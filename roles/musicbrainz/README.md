# musicbrainz

Self-hosted MusicBrainz mirror via the official `metabrainz/musicbrainz-docker`
project. Used by `multi-scrobbler` for unrestricted MB API access (no rate
limits, ~10ms latency vs ~600ms against musicbrainz.org).

Current recovery and maintenance work is tracked in the
[MusicBrainz roadmap](../../docs/musicbrainz-roadmap.md).

The configured target is `v-2026-07-30.1`, PostgreSQL 18, and database schema
31. Production must complete the one-time procedure below before this role is
applied. The role rejects an existing database whose schema does not match the
configured release.

## Layout

The role clones the upstream repo to `/opt/docker/musicbrainz/upstream/` and
drops customizations under `local/`:

- `local/compose/atelier.yml` — Traefik labels + network attachment
- `local/secrets/metabrainz_access_token` — replication token (vault)
- `local/secrets/musicbrainz_healthchecks_url` — replication dead-man URL (vault)
- `local/replication-check.sh` and `local/replication.cron` — monitored replication
- `local/compose.merged.yml` — auto-generated merged compose (see below)
- `.env` — `COMPOSE_FILE` pointing at the merged file, plus version pins

## Why the merged compose file

Upstream `musicbrainz-docker` uses an overlay pattern: you stack multiple
compose files (the base `docker-compose.yml` plus optional `compose/*.yml`
overlays that re-declare a service to add volumes, secrets, etc). Docker
Compose merges them correctly by service name. Komodo's stack parser does
not: it concatenates all the service blocks across files, so a stack that
ultimately runs 6 containers but has 10 service declarations across 4 files
gets flagged `unhealthy` (expected 10, only 6 running).

To sidestep this, the role runs `docker compose -f ... config` on the host
to produce a single fully-resolved compose file at `local/compose.merged.yml`
and points both `.env` (`COMPOSE_FILE=`) and Komodo's `file_paths` at that
one file. The merged file is regenerated on every Ansible run.

Ansible builds local images when the upstream revision or effective build
inputs change, when an image is missing, or when `musicbrainz_force_rebuild`
is true. The normal deployment applies configuration once; there is no later
Compose restart handler. See
[local image builds](../../docs/operations.md#local-image-builds) for fingerprint
and retry behavior.

Implications when something breaks:

- `local/compose.merged.yml` is auto-generated, do not edit by hand. Source
  of truth is `defaults/main.yml` (`musicbrainz_source_compose_files`),
  `templates/local/compose/atelier.yml.j2`, and upstream's files. Re-run the
  role to regenerate.
- Build contexts in the merged file are absolute paths, env vars are
  expanded. The file is host-specific, which is fine since it only lives on
  the host.
- If you add a new overlay (e.g. a dev mode), add it to
  `musicbrainz_source_compose_files` and re-run; do not register it
  separately with Komodo.
- If upstream restructures their compose files, the render task will fail
  loudly at deploy time, not silently.

## Vault keys

`group_vars/musicbrainz/vault.yml` must define:

- `musicbrainz_replication_token` — from `https://metabrainz.org/account/applications`
  (create a "MusicBrainz Replication" token)
- `musicbrainz_healthchecks_url` — dedicated Healthchecks.io ping URL configured
  for `0 3 * * *` UTC with six hours of grace

## First-run import (manual, ~3-6 hours)

After the role completes its first deploy, the stack is up but the database is
empty. Run the upstream import procedure:

```sh
ssh nuc-mini
cd /opt/docker/musicbrainz/upstream
docker compose build                           # ~10 min
tmux new -s mbimport
docker compose run --rm musicbrainz createdb.sh -fetch    # 3-6 hours
# Ctrl-b d to detach; tmux attach -t mbimport to reattach
docker compose up -d
```

`createdb.sh -fetch` downloads the latest MB data dump (~10GB), restores it
into Postgres, and triggers the search indexer to build Solr indexes. It runs
inside a one-shot container — safe to detach via tmux.

## Verification

```sh
# From nuc-mini
curl -fsS 'http://localhost:5000/ws/2/recording/?query=artist:cornelius&fmt=json' | jq '.count'
# Expect: > 0

# From multi-scrobbler container
docker exec multi-scrobbler curl -fsS \
  'http://musicbrainz:5000/ws/2/recording/?query=artist:cornelius&fmt=json' | jq '.count'
```

## Replication

The `compose/replication-cron.yml` overlay binds a crontab into the
`musicbrainz` container. We replace upstream's default crontab (via
`MUSICBRAINZ_CRONTAB_PATH`) with `local/replication.cron`, which runs
`local/replication-check.sh` daily at 03:00 UTC rather than calling
`replication.sh` directly.

MetaBrainz publishes hourly packets and `mirror.sh` applies every pending one
per run, so a successful daily run normally keeps the mirror within a day of
upstream.

### Why the wrapper exists

Upstream's `replication.sh` exits 0 even when the packet fails to apply, and
cron output goes nowhere, so a mirror that has stopped replicating is
indistinguishable from one that is current. Replication broke on 2026-05-11
at the schema 31 change and went unnoticed for three months.

The wrapper writes all output to the container's stdout, judges success from
the database instead of the exit code, and fails if the database cannot be
queried or the last successful replication is older than
`musicbrainz_replication_max_age_hours`. Healthchecks receives start, success,
and failure pings; a missing run is detected independently of the container.

Check it's working:

```sh
# Recent replication activity and wrapper verdicts
docker logs musicbrainz-musicbrainz-1 2>&1 | grep -E 'replication-check|LoadReplication' | tail

# Run it on demand; non-zero exit means the mirror is unhealthy
docker exec musicbrainz-musicbrainz-1 /local/replication-check.sh; echo "exit=$?"

# Ground truth
docker exec musicbrainz-db-1 psql -U musicbrainz -d musicbrainz_db -tAc \
  'SELECT current_schema_sequence, current_replication_sequence, last_replication_date FROM replication_control;'
```

## Schema changes

When `musicbrainz_upstream_version` crosses a schema change (the `-mbdbNN-`
release tags), server code, database schema, PostgreSQL, search indexing, and
the replication boundary can all change together. Bumping the tag as an
ordinary deployment can leave new server code in front of an old database and
make every subsequent packet fail.

Recent schema releases have landed in May:

| Release | Schema |
| --- | --- |
| `v-2022-05-17-mbdb27` | 27 |
| `v-2023-05-15-mbdb28` | 28 |
| `v-2024-05-13-mbdb29-pg16` | 29 |
| `v-2025-05-20.0-mbdb30` | 30 |
| `v-2026-05-11.0-mbdb31-pg18` | 31 |

Treat that timing as a prompt to review upstream, not a guaranteed schedule.
For every schema release, read its release notes and write a release-specific
maintenance plan. Upstream supplied an in-place PostgreSQL 16 to 18 and schema
30 to 31 path in 2026; a generic recreate script would have skipped required
engine, collation, and SIR transitions.

The [roadmap](../../docs/musicbrainz-roadmap.md) records the current schema-31
recovery. Pause routine MusicBrainz deployments from the first host checkout
change until the final version pin is merged and deployed.

## Schema 30 to 31 maintenance

This procedure applies only to the production state recorded on 2026-09-17:
`v-2026-04-27.0`, PostgreSQL 16, schema 30, and replication sequence 185879.
Recheck every precondition before using it. The corrected migration release is
`v-2026-05-13.0-mbdb31-pg18`; the final release is `v-2026-07-30.1`.

Do not run the normal Ansible role until step 8. Run the host commands as root
from `/opt/docker/musicbrainz/upstream`. Keep the same shell open where a step
defines `rollback_stamp` or `COMPOSE_FILE`.

### 1. Record the source state

Open a maintenance window and stop unrelated MusicBrainz deployments. Record
the output of these commands in the maintenance notes:

```sh
ssh nuc
sudo -i
cd /opt/docker/musicbrainz/upstream
git status --short
git describe --tags --always
docker compose ps
docker exec musicbrainz-db-1 psql -U musicbrainz -d musicbrainz_db -tAc \
  'SHOW server_version; SELECT current_schema_sequence, current_replication_sequence, last_replication_date FROM replication_control;'
docker system df
df -h /var/lib/docker
```

Require tag `v-2026-04-27.0`, PostgreSQL 16, and schema 30. Stop if the Git
checkout has an unexplained tracked change, a service is failing, or free disk
is less than the space needed for copies of both persistent volumes plus the
PostgreSQL upgrade.

Confirm that the next packet is the schema boundary:

```sh
docker compose exec -T musicbrainz \
  bash -c 'carton exec -- ./admin/replication/LoadReplicationChanges'
```

The command must report that the packet matches schema 31 while the database
is schema 30. A different result changes the migration starting point; stop and
review upstream instructions again.

The 2026-09-17 inspection found no `amqp` extension, SIR schema, or AMQP
triggers, so the old trigger uninstaller was not required. Recheck instead of
assuming that remains true:

```sh
docker exec musicbrainz-db-1 psql -U musicbrainz -d musicbrainz_db -tAc \
  "SELECT extname FROM pg_extension WHERE extname = 'amqp'; SELECT nspname FROM pg_namespace WHERE nspname = 'sir'; SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND pg_get_triggerdef(oid) ILIKE '%amqp%';"
```

If AMQP triggers are present, run `./admin/setup-amqp-triggers uninstall` on
the schema-30 checkout before continuing.

### 2. Stop writers and create rollback volumes

```sh
docker compose down
rollback_stamp=$(date -u +%Y%m%dT%H%M%SZ)
printf '%s\n' "$rollback_stamp" > /opt/docker/musicbrainz/schema31-rollback-stamp

for source_volume in musicbrainz_pgdata musicbrainz_solrdata; do
  rollback_volume="${source_volume}_schema30_${rollback_stamp}"
  docker volume create "$rollback_volume"
  docker run --rm \
    -v "${source_volume}:/source:ro" \
    -v "${rollback_volume}:/rollback" \
    alpine:3.22 sh -ec 'cp -a /source/. /rollback/'
  source_stats=$(docker run --rm -v "${source_volume}:/data:ro" alpine:3.22 \
    sh -ec 'find /data -type f | wc -l; du -sk /data | cut -f1')
  rollback_stats=$(docker run --rm -v "${rollback_volume}:/data:ro" alpine:3.22 \
    sh -ec 'find /data -type f | wc -l; du -sk /data | cut -f1')
  test "$source_stats" = "$rollback_stats"
  printf '%s -> %s: %s\n' "$source_volume" "$rollback_volume" "$source_stats"
done
```

Both comparisons must succeed. Record the two rollback volume names and their
file-count/size output. Do not restart a writer if either comparison fails.

### 3. Prepare the corrected migration release

```sh
git fetch --tags origin
git checkout v-2026-05-13.0-mbdb31-pg18
cp admin/lib/upgrade-db-schema/musicbrainz-stopped.yml \
  local/compose/musicbrainz-stopped.yml
docker compose \
  -f docker-compose.yml \
  -f compose/replication-token.yml \
  -f local/compose/atelier.yml \
  -f local/compose/musicbrainz-stopped.yml \
  config > local/compose.schema31-migration.yml
export COMPOSE_FILE=local/compose.schema31-migration.yml
docker compose config --services
```

The migration Compose configuration intentionally omits replication cron and
live indexing. It keeps the MusicBrainz container asleep while database work
runs. It must list `db`, `indexer`, `musicbrainz`, `search`, and `valkey`, and
must not list `mq` or `redis`.

### 4. Upgrade PostgreSQL and rebuild collation indexes

```sh
./admin/upgrade-to-postgres18
docker compose exec -T db psql -U musicbrainz -d musicbrainz_db -tAc \
  'SHOW server_version;'
docker compose exec -T musicbrainz bash -c \
  'carton exec -- ./admin/RebuildIndexesUsingCollations.pl --noconcurrently'
```

The upstream upgrader must end with `Upgrade complete!`, and PostgreSQL must
report major version 18. Stop on any other result. The collation command may
emit the version-mismatch warnings documented by upstream, but it must exit
successfully.

### 5. Upgrade the database schema and install SIR

```sh
docker compose build musicbrainz
docker compose up -d musicbrainz indexer
docker compose exec -T musicbrainz upgrade-db-schema.sh
docker compose exec -T db psql -U musicbrainz -d musicbrainz_db -tAc \
  'SELECT current_schema_sequence FROM replication_control;'
./admin/setup-sir install
docker compose exec -T db psql -U musicbrainz -d musicbrainz_db -tAc \
  "SELECT to_regclass('sir.pending_data');"
```

Require schema 31 and relation `sir.pending_data` before continuing.

### 6. Apply the first schema-31 packet

```sh
docker compose exec -T musicbrainz bash -c \
  'carton exec -- ./admin/replication/LoadReplicationChanges --limit=1'
docker compose exec -T db psql -U musicbrainz -d musicbrainz_db -tAc \
  'SELECT current_schema_sequence, current_replication_sequence, last_replication_date FROM replication_control;'
```

Upstream identifies the first packet as beginning at
`2026-05-11 19:54:55.563573+00`. Require schema 31 and a replication sequence
greater than 185879. The documented warning about the packet's old schema
value is expected for this one packet.

### 7. Move to the final release while services remain stopped

```sh
git checkout v-2026-07-30.1
cp admin/lib/upgrade-db-schema/musicbrainz-stopped.yml \
  local/compose/musicbrainz-stopped.yml
docker compose \
  -f docker-compose.yml \
  -f compose/replication-token.yml \
  -f local/compose/atelier.yml \
  -f local/compose/musicbrainz-stopped.yml \
  config > local/compose.schema31-migration.yml
export COMPOSE_FILE=local/compose.schema31-migration.yml
docker compose up --build -d
```

Do not enable replication from this temporary configuration.

### 8. Return ownership to Ansible

Merge the migration PR only after steps 1 through 7 pass. From the merged
repository checkout with the MusicBrainz vault present, apply the normal role:

```sh
make -C deploy musicbrainz
```

The role verifies schema 31 before changing the upstream checkout. It renders
the final Compose configuration with monitored replication and live SIR
indexing, starts Valkey, and removes orphaned RabbitMQ and Redis containers.
Do not use `--check` as a substitute for the maintenance checkpoints.

### 9. Catch up and accept the upgrade

```sh
ssh nuc
sudo -i
cd /opt/docker/musicbrainz/upstream
docker exec musicbrainz-musicbrainz-1 /local/replication-check.sh
docker exec musicbrainz-db-1 psql -U musicbrainz -d musicbrainz_db -tAc \
  'SHOW server_version; SELECT current_schema_sequence, current_replication_sequence, last_replication_date FROM replication_control; SELECT count(*) FROM sir.pending_data;'
docker compose ps
curl -fsS 'http://localhost:5000/ws/2/recording/?query=artist:cornelius&fmt=json' | jq '.count'
```

Repeat the wrapper until it reports no pending packet. Compare the local
sequence with the newest authenticated upstream packet and require replication
age below 36 hours. Wait for `sir.pending_data` to reach zero. `docker compose
ps` must show `db`, `indexer`, `musicbrainz`, `search`, and `valkey`, with no
`mq` or `redis` container. Run the WS/2 check from Multi-Scrobbler and Album
Sort, confirm a successful Healthchecks ping, and repeat the Ansible deployment
to establish idempotence.

Keep both rollback volumes for seven days after acceptance. Removing them and
the orphaned RabbitMQ volume is a separate destructive cleanup requiring
explicit approval.

### Roll back before acceptance

Rollback discards all writes made after the snapshots. Stop the stack and read
the recorded stamp before changing a volume. Restore both members of the
snapshot pair; never restore only PostgreSQL or only Solr.

```sh
cd /opt/docker/musicbrainz/upstream
docker compose down --remove-orphans
rollback_stamp=$(cat /opt/docker/musicbrainz/schema31-rollback-stamp)

for target_volume in musicbrainz_pgdata musicbrainz_solrdata; do
  rollback_volume="${target_volume}_schema30_${rollback_stamp}"
  docker volume inspect "$rollback_volume"
  docker volume rm "$target_volume"
  docker volume create "$target_volume"
  docker run --rm \
    -v "${rollback_volume}:/source:ro" \
    -v "${target_volume}:/restore" \
    alpine:3.22 sh -ec 'cp -a /source/. /restore/'
done

git checkout v-2026-04-27.0
unset COMPOSE_FILE
docker compose up -d
docker exec musicbrainz-db-1 psql -U musicbrainz -d musicbrainz_db -tAc \
  'SHOW server_version; SELECT current_schema_sequence, current_replication_sequence, last_replication_date FROM replication_control;'
```

Require PostgreSQL 16, schema 30, and replication sequence 185879 after the
restore. Keep routine deployments frozen because the repository pin remains
schema 31; repair the migration or prepare a rollback PR before resuming them.

## Notes

- The upstream services (`db`, `search`, `mq`, `valkey`, `indexer`) keep their
  upstream default network and are not exposed externally. Only `musicbrainz`
  joins `proxy` (Traefik) and `shared` (multi-scrobbler ingress + outbound to
  metabrainz.org for replication).
- DB credentials are upstream defaults (`musicbrainz/musicbrainz`) — the DB is
  on an internal-only docker network and is never reachable from the host or
  other stacks, so this is acceptable.
- No backup strategy: the DB is reproducible from upstream dumps. If the
  volume is lost, re-run the import.
