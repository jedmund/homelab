# CI performance on max: September 22, 2026

This records why CI on `max` was slow, what changed, and what the measurements
imply for the next hardware purchase. Album Sort was the subject; the findings
are about the host and the runner, so they apply to every project that builds
here. These are dated observations, not assertions about future host state.

Album Sort's pipeline ran 15–25+ minutes before this work. Over its previous 100
pipelines the median successful run was 21.5 minutes and the 90th percentile
39.5. After the changes below, a full `main` pipeline — validation, tests,
browser suites, image builds and deploy — finished in **7 minutes 43 seconds**.

## What was actually slow

### Disk fsync, not CPU

The single largest factor. Test suites keep SQLite fixtures under
`os.tmpdir()`, which inside a job container is the overlay filesystem on
`/var/lib/docker`. Both NVMe drives are consumer Samsung 990 PROs with no
power-loss protection, so every `fsync` waits for a real flush.

| Target | 4 KiB synchronous writes (`dd oflag=dsync`) |
| --- | --- |
| Host disk (`/var/tmp`) | 844 kB/s — about 4.9 ms per flush |
| RAM (`/dev/shm`) | 3.7 GB/s |

Same container, same 12 CPUs, same 10 Vitest workers, 393 test files passing
either way:

| `/tmp` backing | Wall | Total test time |
| --- | --- | --- |
| Container overlay | 237 s | 1,915 s |
| tmpfs | **66 s** | 474 s |

One migration-checkpoint file went from 104 s to 10 s. The same file takes 16 s
on a developer MacBook, which is what first exposed the gap: macOS `fsync` does
not force a device flush, Linux does. CPU was never the constraint — the host
sat at 94% idle throughout.

### Per-job CPU caps that no suite could use

Every job was capped at 3 CPUs, and the suite ran its test files one at a time
(`fileParallelism: false` in the project's Vitest config), so three CI shards
each worked through ~130 files on a single core. The longest shard was the
pipeline's critical path at 14–26 minutes. Scaling on max, files in parallel:

| Container CPUs | Full suite |
| --- | --- |
| 3 (old cap) | not run to completion; three shards took 16–26 min between them |
| 8 | 350 s |
| 16 | 233 s |

Returns fade past ~16 because one long test file sets a floor.

### Duplicate pipelines

Pushing a branch and then opening its merge request started two full pipelines:
`$CI_OPEN_MERGE_REQUESTS` is still empty at push time, so the `when: never` rule
meant to prevent this cannot match. 20 of 100 pipelines were duplicates, and
they queued against each other on max for up to 8 minutes.

### Setup repeated in every job

Each heavy job spent about 90 s on `apt-get` plus a pip install before doing any
work, and the Storybook job additionally installed Chromium's system
dependencies.

### Type-aware ESLint

157 s of a 232 s validation job. The rules themselves account for ~22 s; the
rest is building a TypeScript program. ESLint 10's `--concurrency` cuts it to
40 s with 4 threads, but each thread holds its own program: 3.3 GB per thread,
11.6 GB peak. That does not fit a 6 GB job, which is why the lint job moved to
the large pool.

## What changed

Host and runner, in this repository:

- A second runner registration on max, `max-docker-large` (2 jobs, 12 CPUs,
  24 GB), alongside the general pool (now 4 jobs, 3 CPUs, 6 GB). See
  [the role runbook](../roles/development_linux/README.md).
- `/tmp` mounted as tmpfs on both pools: 2 GB on the general pool, 8 GB on the
  large one.
- Runner 4's ID recorded so its tags reconcile, and added to the Gatus
  liveness checks.

In the Album Sort repository, for reference: Vitest files run in parallel as one
job on the large pool, ESLint runs as its own threaded job there, branch pushes
no longer start pipelines, and the toolchain moved into prebuilt CI images.

## Result

Album Sort `main`, pipeline 4241, against the same jobs before the work:

| Job | Before | After |
| --- | --- | --- |
| Tests | 1,055 s (slowest of 3 shards) | 88 s |
| Validation | 349 s | 77 s, plus a 61 s lint job in parallel |
| e2e build preparation | 147 s | 40 s |
| Browser e2e | 330 s | 273 s |
| Whole pipeline, push to deployed | ~19 min | 7 min 43 s |

Three consecutive test runs on `main` took 88 s, 83 s and 77 s, so the parallel
suite is stable at 10 workers.

## What this means for the next upgrade

[The August 2026 hardware evaluation](../MAX_HARDWARE_UPGRADE.md) recommended
the 32-core 9975WX on the assumption that CI throughput was the binding
constraint. The measurements above point elsewhere. **Memory is the better
purchase.**

Observed on 2026-09-22, with CI idle:

| Signal | Reading |
| --- | --- |
| CPU | load 4.6 of 32 threads; `vmstat` 94% idle |
| Memory | 19 GB used, 64 GB page cache, 4.6 GB already swapped out |
| DIMM slots | 4 of 8 populated (4 × 32 GB G.Skill F5-6400R3239G32GQ, running 5600 MT/s) |
| GPUs | 3 × RTX PRO 6000 96 GB; two at 96.9 GB used |
| llama-swap | 26 GB resident, models mmapped from `/opt/docker/ai/models` |

Filling the four empty slots takes the host to 256 GB and, because this is an
8-channel WRX90 board running on 4 channels, roughly doubles memory bandwidth.
The 64 GB of page cache is model weights: more RAM keeps more models resident
across llama-swap switches instead of re-reading them from disk, and the 4.6 GB
already in swap shows the host has been squeezed. CI's new tmpfs adds up to
24 GB of RAM draw at full occupancy, from the same pool.

A 64-core CPU would not help the workloads running here. It cannot make one
pipeline faster (same 5.4 GHz boost), it does nothing for GPU inference, and
the CI concurrency it would unlock is bounded by memory first: at 24 GB per
large slot, five slots would want 120 GB of the host's 125 GB. Buy identical
modules or a fresh 8 × 32 GB kit — mixed kits on WRX90 commonly train down or
fail to post.

Revisit if large CPU-offload MoE inference becomes routine, or if CI queue
depth on max grows. Neither was true on this date.
