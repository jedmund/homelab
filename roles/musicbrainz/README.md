# musicbrainz

Self-hosted MusicBrainz mirror via the official `metabrainz/musicbrainz-docker`
project. Used by `multi-scrobbler` for unrestricted MB API access (no rate
limits, ~10ms latency vs ~600ms against musicbrainz.org).

Current recovery and maintenance work is tracked in the
[MusicBrainz roadmap](../../docs/musicbrainz-roadmap.md).

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
recovery. Keep the configured release pinned until that maintenance reaches
its version-pin step. Pause routine MusicBrainz deployments while the host is
temporarily ahead of the repository.

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
