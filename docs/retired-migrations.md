# Retired migrations

Read-only checks on 2026-09-16 confirmed the following migrations on
`nuc-mini`, their sole target in the current inventory. Their one-time tasks
have been removed from routine roles. No host files, volumes, or containers
were deleted during this cleanup.

| Migration | Completion evidence |
| --- | --- |
| Gateway split | Traefik, PocketID, TinyAuth, Line, OpenSpeedTest, and ddclient are running under their respective Compose projects, rather than `infra-gateway`. |
| Gateway state | Traefik mounts its nonempty ACME store under `/opt/docker/traefik`; PocketID and Line mount populated database directories under `/opt/docker/pocketid` and `/opt/docker/line`. |
| Kizuna Garage to NAS | `/opt/docker/kizuna/.garage-data-migrated-to-nas` exists; the running Garage container mounts `kizuna-garage-data-nas`, whose driver options identify the Files NAS path. |
| HuggingHack SQLite to PostgreSQL and PocketID linking | Both `.sqlite-postgres-migrated` and `.pocketid-owner-linked` exist under `/opt/docker/hugginghack/data`; PostgreSQL contains exactly one user with ID `local` and username `jedmund`. The ongoing owner-integrity check remains in the role. |
| Kibble ONVIF alias IPs to macvlan | The old networkd drop-in is absent, `br0` has no feeder alias IPs, and `onvif0` through `onvif2` hold the feeder addresses on macvlan interfaces. |

## Historical implementation and recovery

The complete pre-retirement tasks and defaults are preserved in Git at
`52870726a0bc1236edd6fa177d59714afe599f89`. For example:

```sh
git show 52870726a0bc1236edd6fa177d59714afe599f89:roles/pocketid/tasks/main.yml
git show 52870726a0bc1236edd6fa177d59714afe599f89:roles/kizuna/tasks/main.yml
git show 52870726a0bc1236edd6fa177d59714afe599f89:roles/hugginghack/tasks/main.yml
```

The gateway migration released old container names, copied Traefik's ACME
store, and moved PocketID and Line data to their dedicated stack directories.
Kizuna stopped writers before copying local Garage object blocks to NFS.
HuggingHack took a SQLite backup, migrated and verified PostgreSQL data, then
linked the retained owner to PocketID. Kibble removed bridge aliases before
configuring the macvlan interfaces.

For a host or backup predating these migrations, review the historical tasks
and matching defaults before using the current roles. Restoring old data
requires a separate migration procedure; routine deployment no longer
performs these conversions. Retained legacy data is a historical snapshot
and must not overwrite newer production data.

## Cleanup still pending

`kalay-mock.service` is inactive, but `/etc/systemd/system/kalay-mock.service`
and `/opt/kalay-mock` still exist on `nuc-mini`. The Petlibro removal tasks and
Kibble stop/disable guard remain until that cleanup has completed.
