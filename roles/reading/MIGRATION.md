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
- bind-mounted dirs under `~/docker/reading/...`
- docker named volumes named `reading_karakeep-data` and
  `reading_karakeep-meilisearch`

Today, both live under `media-consumption_*`. We move them.

### 2a. Render the new stack to disk without starting it

Run ansible with `--check` first so you can see exactly what will
change, then deploy. The first real deploy will create the host
directories and pull the images. We'll bring containers up only after
the data is in place.

```bash
# Dry-run
make deploy-reading-check

# Real run that will try to start containers. Either way, we'll stop
# them immediately to do the data move. (Or wrap with --skip-tags if
# you add a tag to the docker_compose_v2 task in roles/reading/tasks/main.yml.)
make deploy-reading

# Stop the freshly-started reading containers so the volumes are quiet
ssh nuc-mini 'cd ~/docker/reading && docker compose down'
```

### 2b. Stop the soon-to-be-moved services in the old stack

```bash
ssh nuc-mini
cd ~/docker/media-consumption
docker compose stop \
  miniflux miniflux-db miniflux-db-backup reactflux \
  karakeep karakeep-chrome karakeep-meilisearch kavita
docker compose rm -f \
  miniflux miniflux-db miniflux-db-backup reactflux \
  karakeep karakeep-chrome karakeep-meilisearch kavita
```

### 2c. Move bind-mounted host directories

```bash
sudo mv data/miniflux-db ~/docker/reading/data/miniflux-db
sudo mv backups/miniflux ~/docker/reading/backups/miniflux
sudo mv config/kavita   ~/docker/reading/config/kavita
```

### 2d. Copy Karakeep named volumes between compose projects

Named volumes are scoped to the compose project name, so the new
`reading_karakeep-*` volumes start empty. Tar-pipe the contents over:

```bash
for vol in karakeep-data karakeep-meilisearch; do
  docker run --rm \
    -v media-consumption_${vol}:/from \
    -v reading_${vol}:/to \
    alpine sh -c 'cd /from && tar cf - . | (cd /to && tar xf -)'
done
```

### 2e. Bring the new stack up

```bash
cd ~/docker/reading
docker compose up -d
```

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

- `~/docker/media-consumption/data/miniflux-db/` (if you used `mv`,
  data is now under `reading/`, so reverse the `mv`)
- `media-consumption_karakeep-data` and `media-consumption_karakeep-meilisearch`
  docker volumes (we only copied, didn't delete)

Bring the original `media-consumption` services back by reverting the
git changes to `roles/media_consumption/` and `roles/reading/`, then
`make deploy-media-consumption`.
