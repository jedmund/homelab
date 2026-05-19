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

Pattern: deploy the role normally (same as every other stack — no
special tags or split phases), then perform a one-time docker-compose
level data swap, then bring containers back up against the migrated
data.

The new stack expects:
- bind-mounted dirs under `/opt/docker/reading/...`
- docker named volumes named `reading_karakeep-data` and
  `reading_karakeep-meilisearch`

Both are created automatically by the initial `make deploy-reading`
run. We populate them after the fact and restart.

### 2a. Dry-run

```bash
make deploy-reading-check
```

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

Leave the old bind-mount dirs + named volumes on disk for rollback
safety — we'll prune them later.

### 2c. Deploy the `reading` stack normally

```bash
make deploy-reading
```

This is a vanilla deploy: ansible creates dirs, drops compose + env
files, and brings containers up. Miniflux's Postgres initializes a
fresh empty DB; Karakeep's named volumes are created empty. That's
fine — we'll replace the data in the next steps.

### 2d. Stop the new stack (one-time, for the data swap)

```bash
ssh nuc-mini 'cd /opt/docker/reading && docker compose down'
```

### 2e. Move bind-mounted host directories

Ansible created the leaf dirs as empty placeholders, and Postgres
populated `data/miniflux-db` on first start. Remove both so the `mv`
lands in the right place instead of nesting.

```bash
ssh nuc-mini
sudo rm -rf /opt/docker/reading/data/miniflux-db
sudo rmdir /opt/docker/reading/backups/miniflux \
           /opt/docker/reading/config/kavita

sudo mv /opt/docker/media-consumption/data/miniflux-db \
        /opt/docker/reading/data/miniflux-db
sudo mv /opt/docker/media-consumption/backups/miniflux \
        /opt/docker/reading/backups/miniflux
sudo mv /opt/docker/media-consumption/config/kavita \
        /opt/docker/reading/config/kavita
```

`rm -rf` on `data/miniflux-db` because Postgres seeded it with a
fresh empty cluster during 2c; the other two are empty placeholders
so `rmdir` is enough.

### 2f. Repopulate Karakeep named volumes

The new `reading_karakeep-*` volumes were created empty by step 2c.
Tar-pipe the old contents in (the source volumes still exist under
their `media-consumption_*` names):

```bash
for vol in karakeep-data karakeep-meilisearch; do
  docker run --rm \
    -v media-consumption_${vol}:/from \
    -v reading_${vol}:/to \
    alpine sh -c 'cd /to && rm -rf ./* ./.[!.]* 2>/dev/null; cd /from && tar cf - . | (cd /to && tar xf -)'
done
```

The `rm` inside clears whatever Karakeep/Meilisearch wrote to the new
empty volume during step 2c before copying the real data in.

### 2g. Bring the stack back up

```bash
ssh nuc-mini 'cd /opt/docker/reading && docker compose up -d'
```

Postgres reads the moved data dir, Karakeep reads the populated
volumes, history is intact.

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
