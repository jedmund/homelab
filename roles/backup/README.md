# backup

Borgmatic running on `nuc-mini` with a local Borg repo at `/var/backup/borg`.
Each successful backup rsync's new segment files to an NFS-mounted UniFi
Drive share at `/mnt/nas/backup`, where the existing UniFi → Backblaze sync
picks them up.

## Layout

- **Borgmatic container** (built locally, extends
  `ghcr.io/borgmatic-collective/borgmatic` with `rsync` + `nfs-common`) runs
  continuously and triggers backups via internal cron at the configured
  schedule (default `02:00` daily).
- **Source paths:** `/opt/docker` (excludes `musicbrainz`, which is
  reproducible from upstream MetaBrainz dumps).
- **Repo:** `/var/backup/borg` on local disk, encrypted with
  `repokey-blake2`.
- **Retention:** `keep_daily: 30` — snapshots roll off after one month.
- **Mirror to NAS:** borgmatic's `after_actions` hook runs
  `/scripts/post-backup-rsync.sh` inside the container, which rsync's the
  repo to `/nas/borg-nuc-mini/`.

## Vault keys

Create `group_vars/backup/vault.yml` with `ansible-vault` and add:

```yaml
borg_passphrase: <strong random string, 32+ chars>
```

Generate one with `openssl rand -base64 48` or similar. **Save it
somewhere outside this repo too** — losing the passphrase means losing
access to the repo permanently.

## Bootstrap

After the first deploy completes, the local repo at `/var/backup/borg` is
empty. Initialize it once manually:

```sh
ssh nuc-mini
docker exec -it borgmatic bash -c '
    BORG_PASSPHRASE="$(grep ^BORG_PASSPHRASE /etc/borgmatic.d/../env/borgmatic.env | cut -d= -f2)" \
    borg init --encryption=repokey-blake2 /repo
'
```

Or simpler, run the borgmatic init helper:

```sh
docker exec -it borgmatic borgmatic rcreate --encryption repokey-blake2
```

After init, trigger the first backup manually before relying on the cron:

```sh
docker exec borgmatic borgmatic --verbosity 1
```

The first run will take hours depending on data volume; subsequent runs
are minutes due to dedup.

## NAS share setup

The role expects an NFS export reachable at the address configured in
`roles/backup/defaults/main.yml` (`nas_nfs_server` + `nas_nfs_export`).
On the UniFi Drive side:

1. Create a share named `homelab-backup` (or adjust `nas_nfs_export` in
   defaults).
2. Enable NFS access for the share.
3. Permit the nuc-mini IP in the NFS access list.

The Ansible role mounts it at `/mnt/nas/backup` via a systemd
`.automount` unit so a NAS hiccup doesn't block boot — the mount activates
on first access.

## Verification

Check borgmatic's last run:

```sh
docker logs borgmatic | tail -50
```

List archives:

```sh
docker exec borgmatic borg list /repo
```

Browse a snapshot:

```sh
docker exec borgmatic borg mount /repo::nuc-mini-2026-05-10T02:00:00 /tmp/snapshot
ls /tmp/snapshot
docker exec borgmatic borg umount /tmp/snapshot
```

Confirm rsync to NAS is working:

```sh
ls -la /mnt/nas/backup/borg-nuc-mini/
```

Should mirror the structure of `/var/backup/borg/`.

## What's covered

**Native borgmatic hooks** (streamed dump, no temp files):

- 9 PostgreSQL instances: Immich, Mastodon, Synapse, MAS, n8n, Miniflux,
  Forgejo, Blinko, Draftboard
- 1 MariaDB: RomM (via `mariadb_databases` hook, dumped as root)
- 1 MongoDB: Komodo (admin database, full dump)

**Custom `before_backup` scripts** writing to `/var/backup/dumps/`:

- CouchDB (Obsidian LiveSync): per-database JSON dump with attachments
- SQLite: `sqlite3 .backup` snapshots for PocketID, Papra, Homebox,
  album-sort, *arrs (Sonarr/Radarr/Lidarr/Prowlarr), qui, Pinchflat,
  Kavita, Stash, Tunarr

**File-level snapshots** (`/opt/docker`): every stack's bind-mounted
configs, env files (encrypted at rest by borg), and other on-disk state.
Excludes `/opt/docker/musicbrainz` (reproducible from upstream dumps)
and `/opt/docker/backup` (avoid recursive snapshot).

## What's not covered yet

- Web UI for browsing/restore: lands in PR 3 (borg-ui with PocketID OIDC).
- Monitoring: lands in PR 4 (Healthchecks.io plus Netdata scrape).
- Plex's library database: deep path with spaces, deferred. Restoring
  from the bare config dir snapshot can result in inconsistent WAL state
  if Plex was writing during the backup.
- Named docker volumes that aren't covered by DB dumps (e.g. Synapse's
  media store at `matrix_synapse-data`, Mastodon's local media if any).
  TBD whether these need explicit handling.
