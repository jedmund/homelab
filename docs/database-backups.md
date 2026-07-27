# Database backups

The `backup` role owns scheduled Borg backups. This guide covers manual,
application-consistent database dumps for migrations and recovery work.

## PostgreSQL services

| Service | Container | Database | User |
| --- | --- | --- | --- |
| Miniflux | `miniflux-db` | `miniflux` | `miniflux` |
| Immich | `immich-database` | `immich` | `postgres` |
| Dawarich | `dawarich_postgres` | `dawarich_production` | `dawarich` |
| n8n | `n8n_postgres` | `n8n` | `n8n` |
| Blinko | `blinko_postgres` | `blinko` | `blinko` |
| Mastodon | `mastodon-db` | `mastodon_production` | `mastodon` |

GitLab Omnibus uses embedded PostgreSQL and its own backup tooling. A nightly
application-consistent dump is scheduled by `roles/gitlab/tasks/main.yml`;
follow the [GitLab runbook](../roles/gitlab/GITLAB_UPGRADE.md) for maintenance
backups and restores.

### Backup

```sh
docker exec <container> pg_dump -U <user> <database> > backup.sql
```

Examples:

```sh
docker exec miniflux-db pg_dump -U miniflux miniflux > miniflux_backup.sql
docker exec immich-database pg_dump -U postgres immich > immich_backup.sql
docker exec dawarich_postgres pg_dump -U dawarich dawarich_production > dawarich_backup.sql
docker exec n8n_postgres pg_dump -U n8n n8n > n8n_backup.sql
docker exec blinko_postgres pg_dump -U blinko blinko > blinko_backup.sql
docker exec mastodon-db pg_dump -U mastodon mastodon_production > mastodon_backup.sql
```

### Restore

Stop the application container before restoring, then restart it:

```sh
docker stop <app-container>
docker exec -i <container> psql -U <user> <database> < backup.sql
docker start <app-container>
```

## MariaDB services

| Service | Container | Database | User |
| --- | --- | --- | --- |
| RomM | `romm-db` | `romm` | `romm-atelier` |

```sh
# Backup
docker exec romm-db mariadb-dump -u romm-atelier -p<password> romm > romm_backup.sql

# Restore
docker exec -i romm-db mariadb -u romm-atelier -p<password> romm < romm_backup.sql
```

## Migration example

1. Create the dump on the old host and copy it to the new host:

   ```sh
   docker exec immich-database pg_dump -U postgres immich > immich_backup.sql
   scp immich_backup.sql newmachine:/tmp/
   ```

2. Deploy the stack on the new host so its volumes and database exist:

   ```sh
   ansible-playbook deploy/immich.yml
   ```

3. Stop the application, restore the dump, and restart:

   ```sh
   docker stop immich-server
   docker exec -i immich-database psql -U postgres immich < /tmp/immich_backup.sql
   docker start immich-server
   ```

Test restoration in an isolated environment before relying on a dump as a
recovery point. Some services also require non-database files or object
storage; consult that role's README.
