# Migrating to the `reading` stack

This is a **one-time** runbook for splitting Miniflux + Reactflux +
Karakeep + Kavita out of `media_consumption` into a dedicated `reading`
stack, and adding FiveFilters Full-Text RSS.

The repo-side changes are already in place. What's left is:

1. Populating `group_vars/reading/vault.yml`.
2. Migrating on-disk data on `nuc-mini` (one stop-the-world step).
3. Verification + cleanup.

## 1. Bootstrap the new vault

```bash
# Start from a copy of the existing vault (already encrypted, same key)
cp group_vars/media_consumption/vault.yml group_vars/reading/vault.yml

# Edit. Add fivefilters_admin_password. Optionally trim non-reading keys.
make edit-vault FILE=group_vars/reading/vault.yml
```

Required keys (see `group_vars/reading/README.md` for the full list):

- `miniflux_admin_password`, `miniflux_db_password`,
  `miniflux_oauth2_client_id`, `miniflux_oauth2_client_secret`
- `karakeep_nextauth_secret`, `karakeep_meili_master_key`,
  `karakeep_oauth_client_id`, `karakeep_oauth_client_secret`,
  optional `karakeep_openai_api_key`
- **New:** `fivefilters_admin_password`

## 2. Migrate the data on `nuc-mini`

The new stack expects:
- bind-mounted dirs under `/opt/docker/reading/...`
- docker named volumes named `reading_karakeep-data` and
  `reading_karakeep-meilisearch`

Today, both live under `media-consumption_*`. We pre-populate the new
homes, **then** run `make deploy-reading` for the first time, so the
new containers start with data already in place — no bring-up /
tear-down dance.

### 2a. Dry-run the ansible deploy

```bash
make deploy-reading-check
```

Read the diff. Confirm it only touches `/opt/docker/reading/...` and
no other paths.

### 2b. Stop the soon-to-be-moved services in the old stack

```bash
ssh nuc-mini
cd /opt/docker/media-consumption
docker compose stop \
  miniflux miniflux-db miniflux-db-backup reactflux \
  karakeep karakeep-chrome karakeep-meilisearch kavita
docker compose rm -f \
  miniflux miniflux-db miniflux-db-backup reactflux \
  karakeep karakeep-chrome karakeep-meilisearch kavita
```

Leave the old DB data + named volumes on disk for rollback safety —
we'll prune them later.

### 2c. Have ansible create destination directories (no containers yet)

The role's docker_compose_v2 task is tagged `up`, so we can run
everything else first — directories, compose file, env files — without
starting containers.

```bash
ansible-playbook deploy/reading.yml \
  -i inventory/hosts.yml \
  --vault-password-file ~/.ansible-vault-pass \
  --skip-tags up
```

This creates `/opt/docker/reading/{,env,data/miniflux-db,backups/miniflux,config/kavita,config/fivefilters/cache}`
with the right ownership, plus the compose.yaml and env files.

### 2d. Move bind-mounted host directories

Ansible created the leaf dirs as empty placeholders. `rmdir` them
first (`rmdir` only removes empty dirs, so it's safe) so the `mv`
lands in the right place instead of nesting.

```bash
sudo rmdir /opt/docker/reading/data/miniflux-db \
           /opt/docker/reading/backups/miniflux \
           /opt/docker/reading/config/kavita

sudo mv /opt/docker/media-consumption/data/miniflux-db \
        /opt/docker/reading/data/miniflux-db
sudo mv /opt/docker/media-consumption/backups/miniflux \
        /opt/docker/reading/backups/miniflux
sudo mv /opt/docker/media-consumption/config/kavita \
        /opt/docker/reading/config/kavita
```

### 2e. Copy Karakeep named volumes between compose projects

Named volumes are scoped to the compose project name. Create the new
destinations and tar-pipe the contents across:

```bash
docker volume create reading_karakeep-data
docker volume create reading_karakeep-meilisearch

for vol in karakeep-data karakeep-meilisearch; do
  docker run --rm \
    -v media-consumption_${vol}:/from \
    -v reading_${vol}:/to \
    alpine sh -c 'cd /from && tar cf - . | (cd /to && tar xf -)'
done
```

### 2f. Start the stack

```bash
make deploy-reading
```

Same playbook, this time without `--skip-tags up`. Directories and
templates are already in place (idempotent no-ops); ansible just runs
the docker_compose_v2 task, which starts containers against the
populated data. Postgres reads the moved data dir; Karakeep reads the
populated volumes.

## 3. Verify

```bash
ssh nuc-mini 'docker ps --format "{{.Names}}\t{{.Status}}"' \
  | grep -E 'miniflux|reactflux|fivefilters|karakeep|kavita'

# FiveFilters end-to-end test:
curl -s 'http://nuc-mini:8181/makefulltextfeed.php?url=https%3A%2F%2Fgematsu.com%2Ffeed&max=2' \
  | head -100
```

Browser checks:

- `https://rss.atelier.house` — Miniflux loads, OIDC works, feed
  history intact.
- `https://keep.atelier.house` — Karakeep loads with prior bookmarks +
  tags; trigger a re-crawl on one bookmark.
- `https://kv.atelier.house` — Kavita lists series from the `comics`
  NFS volume.
- `https://read.atelier.house` — Reactflux works.

In Miniflux, edit the Gematsu feed:

- Old URL: `https://gematsu.com/feed`
- New URL: `http://fivefilters/makefulltextfeed.php?url=https%3A%2F%2Fgematsu.com%2Ffeed&max=20`

Hit Refresh. New entries should arrive with body HTML + images.

## 4. Redeploy media and clean up

```bash
make deploy-media-consumption
ssh nuc-mini 'docker ps' | grep -E 'romm|plex|tunarr|stash|scrobble'
```

`remove_orphans: true` should drop the moved containers from the
`media-consumption` compose project automatically.

After everything's been healthy for a day or two:

```bash
ssh nuc-mini 'docker volume rm \
  media-consumption_karakeep-data \
  media-consumption_karakeep-meilisearch'

# Also trim the moved keys from the media_consumption vault
make edit-vault FILE=group_vars/media_consumption/vault.yml
```

## Rollback

If anything goes sideways before the cleanup step, the old data is
still intact:

- `/opt/docker/media-consumption/data/miniflux-db/` (if you used `mv`,
  data is now under `reading/`, so reverse the `mv`)
- `media-consumption_karakeep-data` and `media-consumption_karakeep-meilisearch`
  docker volumes (we only copied, didn't delete)

Bring the original `media-consumption` services back by reverting the
git changes to `roles/media_consumption/` and `roles/reading/`, then
`make deploy-media-consumption`.
