# GitLab upgrade runbook

This repository manages the GitLab CE server and the `nuc-mini-docker`
runner with `roles/gitlab`, and the `max-docker` runner with
`roles/development_linux`. The GitLab Compose project lives at
`/opt/docker/gitlab` on `nuc-mini`.

The instance was upgraded from GitLab 17.5.2 to 19.2.0 on 2026-07-24.
Recheck GitLab's current upgrade path and version notes before using this
runbook for a later release.

## Current versions

| Component | Version |
| --- | --- |
| GitLab CE | `19.2.0-ce.0` |
| `nuc-mini-docker` runner, ID 1 | `19.2.0` |
| `max-docker` runner, ID 3 | `19.2.0` |
| Embedded PostgreSQL | `17.10` |
| `mac-mini-xcode` runner, ID 2 | Stale; keep paused |

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

## Invariants

- Pause and drain all runners before changing the server.
- Leave runners paused until the final version passes every validation.
- Take a database and `/etc/gitlab` backup under the exact current GitLab
  version before each hop.
- Never advance while a regular or batched background migration is incomplete
  or failed.
- Never restore a backup into a different GitLab version or edition.
- Keep runner major/minor versions aligned with the server.
- Leave the stale Mac runner paused until that host is repaired and upgraded.

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
for runner_id in 1 3; do
  glab api --method PUT "runners/${runner_id}" -F paused=false --silent
done

for runner_id in 1 3; do
  glab api "runners/${runner_id}" |
    jq '{id, status, paused, version, revision, contacted_at, job_execution_status}'
done
```

Both active runners must be online on the intended version. Keep runner 2
paused while it remains stale.

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
