# musicbrainz

Self-hosted MusicBrainz mirror via the official `metabrainz/musicbrainz-docker`
project. Used by `multi-scrobbler` for unrestricted MB API access (no rate
limits, ~10ms latency vs ~600ms against musicbrainz.org).

## Layout

The role clones the upstream repo to `/opt/docker/musicbrainz/upstream/` and
drops customizations under `local/`:

- `local/compose/atelier.yml` — Traefik labels + network attachment
- `local/secrets/metabrainz_access_token` — replication token (vault)
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
`local/replication-check.sh` daily at 03:00 rather than calling
`replication.sh` directly.

MetaBrainz publishes hourly packets and `mirror.sh` applies every pending one
per run, so a daily run keeps the mirror within a day of upstream.

### Why the wrapper exists

Upstream's `replication.sh` exits 0 even when the packet fails to apply, and
cron output goes nowhere, so a mirror that has stopped replicating is
indistinguishable from one that is current. Replication broke on 2026-05-11
at the schema 31 change and went unnoticed for three months.

The wrapper writes all output to the container's stdout, judges success from
the database instead of the exit code, and fails when the last successful
replication is older than `musicbrainz_replication_max_age_days`. Set
`musicbrainz_healthchecks_url` to also get an external dead-man's switch.

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

MusicBrainz schema changes are **not upgradable in place**: upstream ships no
migration path and documents recreating the database from a fresh dump. When
`musicbrainz_upstream_version` crosses a schema change (the `-mbdbNN-` release
tags), replication rejects every packet with:

```
This replication packet matches schema sequence #NN, but the database is
currently at #NN-1. You must upgrade your database
```

Bumping the version alone is not enough, and worse, it leaves schema-N server
code running against a schema-(N-1) database. Pair the bump with a recreate,
following upstream's "Recreate database with indexed search" procedure. It
re-downloads the full dumps and rebuilds the search indexes, so expect it to
take hours and to leave the mirror unavailable throughout.

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
