# Backup

Deploys Borgmatic and Borg UI on `nuc-mini`. Borgmatic writes an encrypted
local repository and mirrors it to an NFS share after archive creation.
This role does not back up every homelab host or every Docker volume.

## Configuration

[defaults/main.yml](defaults/main.yml) defines the schedule, retention,
source paths, named volumes, exclusions, and NAS destination.

| Setting | Default |
| --- | --- |
| Local repository | `/var/backup/borg`, mounted at `/repo` |
| Database dump directory | `/var/backup/dumps`, mounted at `/dumps` |
| NAS mount | `/mnt/nas/backup`, mounted at `/nas` |
| NAS destination | `borg-nuc-mini` under the configured Homelab share |
| Schedule | `0 2 * * *`, using the configured timezone |
| Run at container startup | Disabled |
| Encryption | `repokey-blake2` |
| Retention | 30 daily archives matching `nuc-mini-*` |
| Repository check | Weekly |
| Archive check | Monthly |

Archive names use the stable repository label rather than the container ID.
Archives with other names, including historical container-ID prefixes, are
outside the configured prune pattern.

Set `borg_passphrase` and `borg_healthchecks_url` in
`group_vars/backup/vault.yml`. The generated Borgmatic configuration contains
database credentials and is written with mode `0600`. Preserve a recovery
copy of the repository credentials outside the backup host.

## Initial deployment

The NAS export must exist and permit `nuc-mini`. Use `nas_nfs_server` and
`nas_nfs_export` from the defaults for the actual export path. The role creates
a systemd automount at `nas_mount_host_path`.

From the repository root:

```sh
make -C deploy syntax STACK=backup
make deploy-backup
```

For a new, empty repository only, run on `nuc-mini`:

```sh
docker exec -it borgmatic borgmatic rcreate --encryption repokey-blake2
```

Then create an archive and inspect the result:

```sh
docker exec borgmatic borgmatic create --verbosity 1
docker exec borgmatic borgmatic rlist
```

Do not reinitialize an existing repository during a routine deployment.

## Configured coverage

The database hooks are defined in
[borgmatic.yaml.j2](templates/borgmatic.yaml.j2). The current PostgreSQL list
covers Immich, Mastodon, Synapse, MAS, n8n, Miniflux, Dawarich, Kaneo, Kizuna,
and HuggingHack. Native hooks also dump RomM's MariaDB and Komodo's MongoDB.

| Source | Method |
| --- | --- |
| PostgreSQL, MariaDB, MongoDB | Native Borgmatic database hooks |
| Obsidian LiveSync CouchDB | Custom pre-create dump script |
| Selected SQLite databases | Custom pre-create script; see consistency limits below |
| `/opt/docker` | File-level backup, subject to exclusions |
| `/var/backup/dokploy` | VM dump artifacts produced by the Dokploy host role |
| `karakeep-data` | Read-only named-volume mount |
| Kizuna and Kaneo Garage metadata | Read-only named-volume mounts, including their periodic metadata snapshots |

GitLab uses its own scheduled `gitlab-backup create` job. Borgmatic includes
the resulting artifacts under `/opt/docker/gitlab/data/backups`. The GitLab
job currently skips registry and artifacts. The Borgmatic exclusions also
omit live GitLab PostgreSQL, Redis, Prometheus, logs, and registry storage.

Other exclusions include `/opt/docker/musicbrainz` and `/opt/docker/backup`.
Read `borg_exclude_patterns` for the exact list before relying on coverage.

## Consistency and coverage limits

The [SQLite dump script](templates/scripts/dump-sqlite.sh.j2) reads files from
read-only mounts using SQLite's `immutable=1` URI option. Its own implementation
notes that reads concurrent with writes can produce inconsistent snapshots.
A successful command is not proof that every SQLite backup is restorable.
The script skips missing files and returns success if at least one database
dump succeeds. Inspect its per-database results and test restores.

For a controlled SQLite backup before an upgrade, use the application's
supported backup procedure or stop all writers before taking a verified copy.
Do not describe a live file-level copy as an application-consistent backup.

Named volumes are included only when listed in `borg_named_volumes` or covered
by a database hook. For example, Synapse's named media volume is not included
in the current named-volume list. Database coverage does not imply media or
object-store coverage.

Kizuna and Kaneo Garage object blocks reside on the NAS and are not duplicated
in this local repository. They require a separate NAS backup. Use Garage's
metadata snapshots for recovery, with compatible object data. Control-machine
vault files and credentials also require a separate backup.

## NAS mirror

The post-create script uses `rsync --delete` to mirror `/repo` into the NAS
subdirectory. It refuses to run unless `/nas` is an NFS mount. The Compose
bind uses `rslave` propagation so a host automount becomes visible inside the
container.

The mirror is a replica, not a separate retention policy. Deletions in the
local repository are propagated on a later mirror run. The script runs after
`create`; it is not a general post-action sync hook.

Any NAS-to-offsite replication is configured outside this repository. Verify
its status separately from the local Borgmatic run.

## Verify and restore

Run on `nuc-mini`:

```sh
docker logs --tail=100 borgmatic
docker exec borgmatic borgmatic rlist
findmnt -T /mnt/nas/backup
ls -ld /mnt/nas/backup/borg-nuc-mini
```

Confirm the expected archive exists, each required database dump succeeded,
and the NAS mirror completed. Healthchecks sends `finish` and `fail` events
with logs by default; its alert schedule and grace period are managed outside
this role.

Before restoring production data, restore a selected archive into an isolated
location and validate the database and application files. Identify the
matching application version and encryption keys. Stop affected writers before
replacing data. Native database dumps, custom dump files, and raw volume
files require different restore procedures; consult the deployed Borgmatic
command help and the service's runbook for the artifact being restored.

## Borg UI

Borg UI is exposed at `https://backup.atelier.house` and mounts `/repo`
read-only. Its application state lives in the `borg-ui-data` volume.

Configure authentication in the application's settings after first deployment.
Register a PocketID client using the callback URL shown by the deployed UI,
configure the issuer as `https://id.atelier.house`, and test login. Add the
local repository at `/repo` with its passphrase. These UI settings are not
rendered by Ansible. Repository write operations remain with Borgmatic.
