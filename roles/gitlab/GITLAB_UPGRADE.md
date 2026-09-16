# GitLab upgrade runbook

This repository manages the GitLab CE server and the `nuc-mini-docker`
runner with `roles/gitlab`, and the `max-docker` runner with
`roles/development_linux`. The GitLab Compose project lives at
`/opt/docker/gitlab` on `nuc-mini`.

The instance was upgraded from GitLab 17.5.2 to 19.2.0 on 2026-07-24, then
patched to 19.2.4 on 2026-08-18 for the critical GraphQL advisory
(CVE-2026-19478, CVSS 9.4, and CVE-2026-19650, CVSS 7.1). It moves to 19.3.2 on
2026-09-16 for the critical patch release described below. Recheck GitLab's
current upgrade path and version notes before using this runbook for a later
release.

## Current versions

| Component | Version |
| --- | --- |
| GitLab CE | `19.3.2-ce.0` |
| `nuc-mini-docker` runner, ID 1 | `19.3.3` |
| `max-docker` runner, ID 3 | `19.3.3` |
| Embedded PostgreSQL | `17.10` |
| `mac-mini-xcode` runner, ID 2 | `19.3.3` |

## Path used for the 17.5 to 19.2 upgrade

Never skip a required stop. Use the latest patch release available in every
required minor series.

| Stop | GitLab CE | Runner |
| ---: | --- | --- |
| 1 | `17.5.5-ce.0` | `17.5.5` |
| 2 | `17.8.7-ce.0` | `17.8.5` |
| 3 | `17.11.7-ce.0` | `17.11.4` |
| 4 | `18.2.8-ce.0` | `18.2.2` |
| 5 | `18.5.7-ce.0` | `18.5.0` |
| 6 | `18.8.11-ce.0` | `18.8.0` |
| 7 | `18.11.7-ce.0` | `18.11.4` |
| 8 | `19.2.0-ce.0` | `19.2.0` |

GitLab 18.11 automatically upgraded embedded PostgreSQL from 16 to 17.
PostgreSQL must report version 17 before deploying GitLab 19.

GitLab 18.2.8 can fail
`BackfillSentNotificationsAfterPartition` when an old notification falls
outside the existing partitions. Do not modify the data or mark the migration
finished. GitLab's advisory directs administrators to continue to the required
18.5 stop, where the migration is recreated and rescheduled:

<https://federal-support.gitlab.com/hc/en-us/articles/49353859784852-BackfillSentNotificationsAfterPartition-fails-after-upgrade-to-18-2-8>

## 19.2 to 19.3 (2026-09-16)

19.3.2 is the newest 19.3 patch. It is a critical patch release, so this hop is
not optional maintenance: it fixes CVE-2026-85706 (CVSS 10.0), an
unauthenticated path traversal in the repository commits API that reads
arbitrary files off the server, and CVE-2026-87719 (CVSS 9.9), insecure
deserialization in the GraphQL subscription serializer, among 17 fixes in all.
19.2.4 is vulnerable to both.

| Stop | GitLab CE | Runner |
| ---: | --- | --- |
| 1 | `19.3.2-ce.0` | `19.3.3` |

Only one stop. The required stops in 19.x are 19.2, 19.5, 19.8, and 19.11, and
the instance already sits on the 19.2 stop, so 19.2.4 goes straight to 19.3.2
with nothing in between. This is still a minor hop and does carry schema and
background migrations, so run the full per-hop procedure below, not the
shortened patch procedure.

The runner series is one patch ahead of the server at `19.3.3`. That is fine:
only major/minor have to match.

PostgreSQL does not move. 17 remains the 19.x minimum and the embedded cluster
stays on 17.10. GitLab 19.3 offers PostgreSQL 18.4, but only as an opt-in for
fresh Linux package installations; GitLab does not support upgrading an
existing cluster to it yet. Do not attempt `pg-upgrade`.

### require_sha_for_merge on new groups

GitLab 19.2 introduced `require_sha_for_merge`, and on the affected patch
levels every newly created group gets it enabled by default. The merge a merge
request API endpoint then rejects any call that omits a valid commit `sha`,
which breaks automation that merges through the API.

| Release | Affected patches | Fixed in |
| --- | --- | --- |
| 19.2 | `19.2.0` - `19.2.5` | `19.2.6` |
| 19.3 | `19.3.0` - `19.3.1` | `19.3.2` |

The instance has been running an affected version since the 19.2.0 hop on
2026-07-24, so this upgrade stops the problem for groups created from now on
but does not retroactively clear it. Any group created between 2026-07-24 and
this hop may still carry the setting. Existing groups from before 19.2 were
never touched.

This instance was not affected: the check below found no group created in that
window, and all three groups predate 19.2. Rerun it anyway on a later hop, and
on any instance where groups are created more often:

```sh
ssh nuc
docker exec gitlab gitlab-rails runner \
  'pp Group.where("created_at >= ?", Date.new(2026, 7, 24)).map { |g| [g.full_path, g.namespace_settings&.require_sha_for_merge] }'
```

Clear it per group in Settings, General, Merge requests, or leave it on if the
group has no API-driven merges.

### What actually happened

The hop was clean. 19.3.2 came up in a single boot with `RestartCount` 0, so
the automatic mid-upgrade restart seen on the 19.2 hop did not recur. All five
batched background migrations that the upgrade queued drained to zero in about
eight minutes with no failures, and `gitlab:check` and `gitlab:doctor:secrets`
both passed on the first run.

One unrelated task failed partway through the deploy and skipped the container
registry cleanup tasks behind it. MinIO has withdrawn `minio/mc` and
`minio/minio` from Docker Hub, where both now 404, and the CI cache lifecycle
task had been running on a stale locally cached `minio/mc:latest`, because
`docker run` pulls only when the image is absent. The image now comes from
quay.io on a pinned tag. The task carries `no_log: true`, so the playbook
reports nothing but a censored failure: reproduce the rendered `docker run` by
hand on the host to see the real error.

Expect the macOS Local Network gate. The Homebrew upgrade to 19.3.3 installed a
fresh binary and stranded runner 2 exactly as described below.

## Patch releases inside one minor series

A patch hop such as 19.2.0 to 19.2.4 stays inside the same minor series and
carries no database migrations, so it needs no intermediate stop and no
PostgreSQL check. Still honor the invariants below: pause and drain the
runners, take the rollback pair, and require a clean migration gate before and
after. Runners do not need a matching patch version, only a matching
major/minor, so leave them alone unless the advisory names the runner.

Security patch releases are announced on
<https://about.gitlab.com/releases/categories/releases/> and detailed under
<https://docs.gitlab.com/releases/patches/>.

## Invariants

- Pause and drain all runners before changing the server.
- Leave runners paused until the final version passes every validation.
- Take a database and `/etc/gitlab` backup under the exact current GitLab
  version before each hop.
- Never advance while a regular or batched background migration is incomplete
  or failed.
- Never restore a backup into a different GitLab version or edition.
- Keep runner major/minor versions aligned with the server.
- After upgrading the macOS runner, confirm it actually reconnects. See the
  macOS Local Network section below.

## Prepare and drain CI

Record and pause the runners:

```sh
glab api runners/all --paginate |
  jq '.[] | {id, description, paused, status}'

for runner_id in 1 2 3; do
  glab api --method PUT "runners/${runner_id}" -F paused=true --silent
done
```

List nonterminal builds from the GitLab container and wait for running jobs to
finish:

```sh
ssh nuc
docker exec gitlab gitlab-rails runner \
  'pp Ci::Build.where(status: %w[created preparing pending running canceling waiting_for_resource]).pluck(:id, :status, :name)'
```

Confirm that no runner host still has a job container. A GitLab job that is
stuck in `canceling` must not be force-completed until its process/container is
confirmed absent.

## Initial recovery point

Before the first hop, create a full application backup, configuration backup,
and a Borg archive that includes the bind-mounted registry and GitLab data:

```sh
ssh nuc
docker exec -t gitlab gitlab-backup create
docker exec -t gitlab gitlab-ctl backup-etc
```

Verify the archives and `gitlab-secrets.json`; record their names in the
maintenance notes. The normal scheduled GitLab backup skips large object data,
so it is not a replacement for the initial Borg recovery point.

## Repeat for each version hop

### 1. Require a clean source checkpoint

Check regular and batched migrations:

```sh
ssh nuc
docker exec gitlab gitlab-rake db:migrate:status
docker exec gitlab gitlab-psql -d gitlabhq_production -tAc \
  "SELECT
     count(*) FILTER (WHERE status NOT IN (3,6)) AS unfinished,
     count(*) FILTER (WHERE status = 4) AS failed
   FROM batched_background_migrations;"
```

On GitLab 18.5 and later, also run:

```sh
docker exec gitlab gitlab-rake gitlab:background_migrations:status
```

Both counts must be zero. Background migrations use a 120-second scheduler
interval, so unchanged counts between individual probes do not by themselves
mean the queue is stuck. Inspect job timestamps when needed:

```sql
SELECT
  m.id,
  m.job_class_name,
  m.status,
  count(j.id) AS jobs,
  max(j.finished_at) AS last_job_finished
FROM batched_background_migrations m
LEFT JOIN batched_background_migration_jobs j
  ON j.batched_background_migration_id = m.id
WHERE m.status NOT IN (3, 6)
GROUP BY m.id, m.job_class_name, m.status
ORDER BY m.id;
```

### 2. Create the exact rollback pair

```sh
ssh nuc
docker exec -t gitlab gitlab-backup create \
  SKIP=artifacts,repositories,registry,uploads,builds,pages,lfs,packages,terraform_state
docker exec -t gitlab gitlab-ctl backup-etc
docker exec gitlab sh -lc \
  'ls -lht /var/opt/gitlab/backups | head; ls -lht /etc/gitlab/config_backup | head'
```

Record the backup ID, configuration archive, and current GitLab version.

### 3. Change and validate the pins

Update:

- `gitlab_image` and `gitlab_runner_image` in
  `roles/gitlab/defaults/main.yml`
- `gitlab_runner_linux_image` in
  `roles/development_linux/defaults/main.yml`

Then validate:

```sh
ansible-playbook --syntax-check deploy/gitlab.yml
ansible-playbook --syntax-check deploy/development_linux.yml
git diff --check
```

Linked worktrees do not contain the ignored vault files. Supply their paths
explicitly when deploying; never allow the empty role defaults to overwrite
rendered secrets.

### 4. Pre-pull and deploy

Pre-pull the server and runners in parallel to keep downtime short:

```sh
ssh nuc "docker pull <server-image> && docker pull <runner-image>"
ssh max "docker pull <runner-image>"
```

Deploy the remote runner first, then GitLab:

```sh
ansible-playbook deploy/development_linux.yml \
  -e @/path/to/group_vars/development_linux/vault.yml \
  -e @/path/to/group_vars/gitlab/vault.yml

ansible-playbook deploy/gitlab.yml \
  -e @/path/to/group_vars/gitlab/vault.yml
```

Do not trust Compose container health alone during an Omnibus image upgrade.
The container can report healthy while `gitlab-ctl reconfigure`,
`gitlab:db:configure`, or `pg-upgrade` is still running. Check the process
state and wait for all internal services:

```sh
ssh nuc
docker exec gitlab sh -lc \
  'ps auxww | grep -E "reconfigure|gitlab:db:configure|pg-upgrade|vacuumdb" | grep -v grep || true'
docker exec gitlab gitlab-ctl status
```

GitLab 19.2 performed one automatic container restart before its schema
migrations ran. A Rails missing-column error during that first boot resolved
after the restarted container completed `gitlab:db:configure`. Diagnose the
active reconfigure log before attempting a rollback or manual migration.

### 5. Validate the hop

Require all of these:

```sh
ssh nuc
docker exec gitlab gitlab-ctl status
docker exec gitlab gitlab-rails runner 'puts Gitlab::VERSION'
docker exec gitlab gitlab-psql -d gitlabhq_production -tAc \
  'SHOW server_version'
docker exec gitlab gitlab-rake gitlab:check SANITIZE=true
docker exec gitlab gitlab-rake gitlab:doctor:secrets
docker inspect --format \
  '{{.Name}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}}' \
  gitlab gitlab_runner gitlab-cache-garage
```

From the workstation:

```sh
glab api version
curl -sS -o /dev/null -w '%{http_code}\n' https://git.atelier.house/
curl -sS -o /dev/null -w '%{http_code}\n' https://registry.atelier.house/v2/
```

The UI normally redirects with HTTP 302. The unauthenticated registry probe
normally returns HTTP 401. Repeat the migration gate and wait for zero before
the next hop.

## Restore CI

After the final version is stable and every migration is complete, unpause only
the upgraded runners:

```sh
for runner_id in 1 2 3; do
  glab api --method PUT "runners/${runner_id}" -F paused=false --silent
done

for runner_id in 1 2 3; do
  glab api "runners/${runner_id}" |
    jq '{id, status, paused, version, revision, platform, contacted_at, job_execution_status}'
done
```

All three runners must be online on the intended version. Treat a null
`platform`, `architecture`, or `version` as not connected even when `status`
reads online. GitLab only rewrites `contacted_at` every 40 to 55 minutes, so a
frozen timestamp is not by itself a fault.

## macOS Local Network permission on the Xcode runner

Runner 2 runs from a user LaunchAgent on `mac-mini`, so it is subject to the
macOS Local Network privacy gate. A blocked runner keeps its process alive and
its registration valid while every poll fails against the LAN address:

```
dial tcp 192.168.1.6:443: connect: no route to host
```

The gate keys on the binary, so a Homebrew upgrade of `gitlab-runner` installs
a new binary that has never been approved and silently revokes access. This is
what stranded runner 2 from 2026-07-25 to 2026-08-18: the 19.2.0 hop upgraded
the formula, the new binary was never approved, and nothing surfaced the
failure. Expect it after every macOS runner upgrade.

Diagnose it by proving the network is fine while only the daemon fails:

```sh
ssh mac
nc -zv -w 3 192.168.1.6 443
curl -sS -o /dev/null -w '%{http_code}\n' https://git.atelier.house/
/opt/homebrew/bin/gitlab-runner verify \
  --config /Users/justin/.gitlab-runner/config.toml
tail -3 ~/gitlab-runner.err.log
```

An SSH session inherits a different responsible process than launchd, so those
four succeeding while the daemon logs `no route to host` confirms the gate
rather than a network, DNS, or token fault.

The fix is a GUI action: on `mac-mini`, System Settings, Privacy & Security,
Local Network, enable `gitlab-runner`. A running daemon picks the approval up
within seconds and needs no restart. Confirm by checking that
`~/gitlab-runner.err.log` stops growing and that `platform` and `architecture`
are populated in `glab api runners/2`.

There is no way to pre-approve or disable this. The Local Network list is not
exposed to MDM, and `com.apple.TCC.configuration-profile-policy` carries no
payload for it. Root LaunchDaemons are exempt, but this runner is deliberately
user-mode because system-mode would break Xcode code signing and login keychain
access, so that exemption is not available here.

## Roll back one failed hop

Rollback overwrites the newer database. Use it only when the current hop cannot
be repaired.

1. Keep all runners paused.
2. Revert all three image pins to the immediately preceding version and deploy
   that exact server/runner set.
3. Restore the matching `/etc/gitlab` state if the failed hop changed secrets.
4. Stop Puma and Sidekiq:

   ```sh
   docker exec gitlab gitlab-ctl stop puma
   docker exec gitlab gitlab-ctl stop sidekiq
   ```

5. Restore only the database backup created immediately before the failed hop:

   ```sh
   docker exec -it gitlab gitlab-backup restore \
     BACKUP=<backup-id> \
     SKIP=artifacts,repositories,registry,uploads,builds,pages,lfs,packages,terraform_state
   ```

6. Reconfigure, restart, and rerun every validation gate.

## References

- <https://docs.gitlab.com/update/upgrade_paths/>
- <https://docs.gitlab.com/update/versions/>
- <https://docs.gitlab.com/update/docker/>
- <https://docs.gitlab.com/update/background_migrations/>
- <https://docs.gitlab.com/update/package/downgrade/>
- <https://docs.gitlab.com/update/versions/gitlab_19_changes/>
