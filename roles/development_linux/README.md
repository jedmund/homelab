# GitLab Runner on max

This role deploys a single GitLab Runner process on `max` with the Docker
executor. That one process registers as **two runners**, because tags and the
untagged flag are registration metadata held in GitLab's database, not
settings `config.toml` can declare. One pool takes ordinary jobs, the other
takes jobs that parallelize and need real CPU and memory.

`nuc-mini` runs GitLab itself plus about fifty other stacks and sits near its
load ceiling, so heavy CI belongs here: `max` is a 32-thread Threadripper Pro
whose CPU is nearly idle, since the inference work happens on its GPUs.

## The two pools

| | `max-docker` (id 3) | `max-docker-large` (id 4) |
| --- | --- | --- |
| Tags | `atelier-max`, plus `amd64`/`docker`/`linux`/`pnpm-cache` | `atelier-max-large`, plus the same four |
| Takes untagged jobs | yes | no |
| Concurrent jobs (`limit`) | 4 | 2 |
| Per job | 3 CPUs, 6 GB | 12 CPUs, 24 GB |
| `/tmp` (tmpfs) | 2 GB | 8 GB |

`concurrent` is the sum of both limits. Worst case is 36 CPUs of quota against
32 threads; Docker's `cpus` is a CFS quota rather than pinning, so the host is
only oversubscribed when all six jobs peak at once, and normal mixed CI leaves
room for the CPU side of inference.

Reach the large pool by tagging a job `atelier-max-large`. Use it only for work
that actually uses the slot: it has two slots total, shared by every project on
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
