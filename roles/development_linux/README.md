# GitLab Runner on max

This role deploys a single GitLab Runner process on `max` with the Docker
executor. That one process registers as **two runners**, because tags and the
untagged flag are registration metadata held in GitLab's database, not
settings `config.toml` can declare. One pool takes ordinary jobs, the other
takes jobs that parallelize and need real CPU and memory.

`nuc-mini` runs GitLab itself plus about fifty other stacks and sits near its
load ceiling, so heavy CI belongs here: `max` is a Threadripper PRO 9985WX
workstation (64 cores / 128 threads, 498 GiB visible RAM) that shares CPU and
memory between CI and GPU inference services.

## The two pools

| | `max-docker` (id 3) | `max-docker-large` (id 4) |
| --- | --- | --- |
| Tags | `atelier-max`, plus `amd64`/`docker`/`linux`/`pnpm-cache` | `atelier-max-large`, plus the same four |
| Takes untagged jobs | yes | no |
| Concurrent jobs (`limit`) | 14 | 3 |
| Per job | 6 CPUs, 8 GB | 12 CPUs, 24 GB |
| `/tmp` (tmpfs) | 2 GB | 8 GB |

The process-wide `concurrent` cap is **17**, the sum of the pool limits, so
every slot in both pools can run at once.

The worst case is 120 CPUs of quota against 128 threads, and 184 GB of memory
limits against 498 GiB of RAM. Since the October 24, 2026 upgrade to 512 GB,
CPU quota rather than memory bounds the pools; they stay below the thread count
because inference services share the CPU. Limits are ceilings, not reservations: on
2026-10-16 one full Kizuna app pipeline used about 36 GiB across its jobs, with
browser jobs at 1-4.6 GB and `lint` on the large pool at 9.6 GB. Docker's `cpus`
is a CFS quota rather than pinning or a reservation; simultaneous peaks can
contend with the CPU side of inference. To add capacity, raise the pool
limits and `concurrent` rather than the per-job caps.

Node tools read the quota: inside a 6-CPU job `os.availableParallelism()`
returns 6, so Vitest and pnpm size their workers to it, although coreutils
`nproc` reports all 128 host threads. The runners do not set `cpuset_cpus`. It
applies to a whole runner entry, so every job in a pool would share the same
pinned cores, and a 2026-10-16 test on this host showed Chromium and Firefox
memory unchanged with `--cpuset-cpus=0-2`.

Reach the large pool by tagging a job `atelier-max-large`. Use it only for work
that actually uses the slot: it has three slots total, shared by every project on
this GitLab, and a job pinned to one worker wastes 11 of its 12 CPUs.

## Why /tmp is a tmpfs

Both pools mount `/tmp` as tmpfs. Test suites that keep SQLite databases or
Postgres data under `os.tmpdir()` fsync constantly, and a synchronous 4 KiB
write to this host's NVMe drives takes about 5 ms — they are consumer 990 PROs
with no power-loss protection, so every flush is real. Measured 2026-09-22 with
`dd oflag=dsync`: 844 kB/s on disk against 3.7 GB/s on `/dev/shm`.

Album Sort's Vitest suite, same container and 12 CPUs, took **237 s with /tmp on
the container overlay and 66 s on tmpfs**. Its migration-checkpoint file alone
went from 104 s to 10 s. See
[the CI performance report](../../docs/ci-performance-2026-09-22.md).

tmpfs pages count against the job's memory limit, so each size stays well under
its pool's cap. A job that outgrows its tmpfs gets ENOSPC, not an OOM kill.
Raising a size means lowering the effective memory available to that job.

## Adding or re-registering a runner

Auth tokens come from a runner registration in the GitLab admin UI, never from
`register`/`verify` — this role owns `config.toml` and the runner only writes
back during those commands, which we do not run.

1. GitLab → Admin → Runners → create an instance runner. Set its tags and turn
   off "run untagged" for a tagged-only pool.
2. Put the token in `group_vars/development_linux/vault.yml`
   (`gitlab_runner_linux_auth_token`, `gitlab_runner_linux_large_auth_token`).
3. Record the new runner's ID in `defaults/main.yml`. The large entry is left
   out of `config.toml` entirely until its token exists, and the metadata task
   skips a runner whose ID is still `0` — which is how runner 4 ended up with
   only the tag it was created with until 2026-09-22.
4. `make deploy-development-linux`.

Tags and the untagged flag are reconciled after deployment by a `gitlab-rails`
command delegated to `nuc-mini`, so the desired values live here as code. Order
matters: reconciliation runs after the cache is configured, or a `pnpm-cache`
job could land here before the cache it needs exists.

Both `[[runners]]` entries render from one Jinja macro in
`templates/gitlab-runner/config.toml.j2`, so they cannot drift apart. Add
per-pool differences as macro arguments, not as a second copy of the block.

## Operating notes

- **Config reloads are live.** GitLab Runner watches `config.toml`, so changing
  concurrency, caps or cache does not interrupt jobs in flight. Deploy any time.
- **Verify a deploy:**
  ```sh
  ssh max "docker exec gitlab_runner cat /etc/gitlab-runner/config.toml" \
    | grep -E '^concurrent|name =|limit =|cpus =|tmpfs'
  glab api runners/4   # tags and run_untagged after reconciliation
  ```
- **The local Docker cache is off** (`disable_cache = true`). It backed
  unmapped paths like `/cache` with named volumes that GitLab Runner never
  deletes — 106 volumes and 55 GB on this host before it was disabled. The
  shared Garage S3 cache on `nuc-mini` provides the reuse it was duplicating.
- **inotify instances are raised to 1024.** The kernel default of 128 is not
  survivable for Vite/Vitest jobs; `inotify_init()` starts returning EMFILE
  mid-job even with no fd leak, and raising `ulimit -n` does not help.
- **Gatus watches both runner IDs** (`gatus_gitlab_runners`) for
  `online == true`. A paused runner still reports online, so a deliberate pause
  does not alert. A new pool needs its ID added there too.
