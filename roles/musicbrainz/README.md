# musicbrainz

Self-hosted MusicBrainz mirror via the official `metabrainz/musicbrainz-docker`
project. Used by `multi-scrobbler` for unrestricted MB API access (no rate
limits, ~10ms latency vs ~600ms against musicbrainz.org).

## Layout

The role clones the upstream repo to `/opt/docker/musicbrainz/upstream/` and
drops customizations under `local/`:

- `local/compose/atelier.yml` — Traefik labels + network attachment
- `local/secrets/metabrainz_access_token` — replication token (vault)
- `.env` — `COMPOSE_FILE` overlay list and version pins

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

The `compose/replication-cron.yml` overlay adds a crontab inside the
`musicbrainz` container that runs `replication.sh` hourly. After the import
finishes, replication keeps the mirror within an hour of upstream. Check it's
working:

```sh
docker compose -f /opt/docker/musicbrainz/upstream/docker-compose.yml logs musicbrainz | grep -i replication | tail
```

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
