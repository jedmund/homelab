# Homelab

Ansible playbooks for deploying and managing a homelab infrastructure.

## Structure

```
.
├── deploy/        # One playbook per stack (deploy/all.yml runs everything)
│   └── group_vars -> ../group_vars  # Symlink for variable resolution
├── group_vars/    # Host group variables and vault files
├── inventory/     # Host inventory (hosts.yml)
├── roles/         # One role per stack; see the roster below
├── CONVENTIONS.md # How services are wired up and how to add a new one
└── Makefile       # Deployment commands
```

> **Note:** The `deploy/group_vars` symlink exists because Ansible resolves `group_vars/` relative to the playbook location. Without it, playbooks in `deploy/` wouldn't find variables defined in the root `group_vars/`.

Each stack is its own Ansible role under `roles/`, deployed by the matching
`deploy/<role>.yml` playbook to the host group of the same name in
`inventory/hosts.yml`. Before adding or changing a service, read
[CONVENTIONS.md](CONVENTIONS.md).

### Role roster

In-house (self-developed) services are tagged `[in-house]`; see
[CONVENTIONS.md](CONVENTIONS.md) for how those are built and pulled.

**Base / prerequisites (compute_servers)**
| Role | What it sets up |
|------|-----------------|
| `prerequisites` | DNS fallback, passwordless sudo, shell env |
| `docker` | Docker engine + runtime |
| `networks` | proxy / backend / shared / cibuild / vpn Docker networks |
| `docker-volumes` | NFS-backed Docker volumes (`nfs_volumes`) |
| `firewall` | UFW rules grouped by service |
| `security` | SSH hardening |
| `monitoring` | Netdata (nuc-mini parent, others children) |

**Infrastructure (nuc-mini)**
| Role | Services |
|------|----------|
| `infra_gateway` | Traefik, PocketID, TinyAuth, ddclient, AdGuard, OpenSpeedTest, Line `[in-house]` |
| `infra_core` | Komodo (Core + Periphery + MongoDB) |
| `dokploy_host` | KVM VM (libvirt) hosting Dokploy |

**Media (nuc-mini)**
| Role | Services |
|------|----------|
| `media_acquisition` | Prowlarr, Sonarr, Radarr, Lidarr, qBittorrent, Gluetun, slskd |
| `media_consumption` | Plex, Romm, Tunarr, Stash, Multi-Scrobbler |

**Product stacks (nuc-mini)**
| Role | Services |
|------|----------|
| `immich` | Immich server, machine learning, Redis, Postgres |
| `papra` | Papra |
| `homebox` | Homebox |
| `album_sort` | Album Sort `[in-house]`, Beets |
| `dawarich` | Dawarich app, Sidekiq, Postgres, Redis, Photon |
| `miniflux` | Miniflux, Postgres, backup helper, Reactflux, FiveFilters |
| `karakeep` | Karakeep, Chrome, Meilisearch |
| `kavita` | Kavita |
| `strudel` | Strudel `[in-house]` |
| `blinko` | Blinko, Postgres |
| `obsidian_livesync` | CouchDB backend for Obsidian LiveSync |
| `n8n` | n8n, Postgres |
| `changedetection` | ChangeDetection.io |
| `copyparty` | Copyparty |

**Content and social (nuc-mini)**
| Role | Services |
|------|----------|
| `social` | Mastodon (+ Postgres, Redis, streaming) |
| `matrix` | Synapse, MAS (+ Postgres) |
| `musicbrainz` | MusicBrainz mirror |

**Utilities (nuc-mini)**
| Role | Services |
|------|----------|
| `feederhub` | feederhub `[in-house]` |
| `vane` | Vane `[in-house]` |
| `petlibro` | catbro `[in-house]`, Mosquitto |

**Development (nuc-mini + mac-mini)**
| Role | Services |
|------|----------|
| `development` | GitLab, GitLab Runner (Docker), Renovate, Open WebUI, Paseo relay |
| `development_macos` | GitLab Runner (shell executor, iOS builds) |
| `openclaw` | OpenClaw agent (native macOS) |
| `paseo_daemon` | Paseo daemon (native macOS) |

**AI / GPU (max)**
| Role | Services |
|------|----------|
| `ai` | llama-swap, Whisper, Kokoro, TEI, SearXNG, Playwright |
| `vllm` | DeepSeek V4 Flash (active serving path, port 11437) |
| `sglang` | SGLang stack (parked; see `roles/sglang/README.md`) |
| `gpu_tools` | hwsummary, gpu-burn helper scripts |

**Other**
| Role | Services |
|------|----------|
| `backup` | Borgmatic + Borg-UI (nightly Borg snapshots) |
| `dokploy` | Dokploy bootstrap (runs inside the dokploy_host VM) |

## Prerequisites

- Ansible 2.9+
- SSH access to target hosts
- Python 3.x on target hosts

## Setup

1. Clone the repository
2. Run initial setup:
   ```
   make setup
   ```
3. Update the inventory file (see Inventory Configuration below)
4. Configure vault files (see Vault Variables below)
5. Test connectivity:
   ```
   make test-connection
   ```

## Inventory Configuration

Edit `inventory/hosts.yml` to define your hosts and assign them to stack groups.

### Host Configuration

Each host requires the following variables:

| Variable | Description |
|----------|-------------|
| `ansible_host` | IP address or hostname of the target machine |
| `ansible_port` | SSH port (omit if using default port 22) |
| `ansible_user` | SSH username |
| `ansible_connection` | Set to `local` if running against the local machine |

Example host entry:

```yaml
compute_servers:
  hosts:
    my-server:
      ansible_host: 192.168.1.100
      ansible_port: 22
      ansible_user: myuser
```

### Stack Group Assignment

Assign hosts to stack groups to control which services get deployed to each machine. Add your host under the appropriate group:

```yaml
infra_gateway:
  hosts:
    my-server:

media_consumption:
  hosts:
    my-server:
```

A single host can belong to multiple groups.

## Vault Variables

Each stack requires secrets stored in encrypted vault files. Create these files and encrypt them with `ansible-vault`.

### group_vars/compute_servers/vault.yml

Shared secrets used by multiple stacks.

| Variable | Description |
|----------|-------------|
| `sendgrid_api_key` | SendGrid SMTP API key (used by Mastodon and Dawarich) |

### group_vars/infra_core/vault.yml

#### Komodo

| Variable | Description |
|----------|-------------|
| `komodo_db_username` | MongoDB username |
| `komodo_db_password` | MongoDB password |
| `komodo_init_admin_username` | Initial admin username |
| `komodo_init_admin_password` | Initial admin password |
| `komodo_jwt_secret` | JWT signing secret |
| `komodo_passkey` | Passkey for periphery authentication |
| `komodo_webhook_secret` | Webhook signing secret |
| `komodo_oidc_client_secret` | OIDC client secret (if using SSO) |

### group_vars/infra_gateway/vault.yml

#### Traefik

| Variable | Description |
|----------|-------------|
| `traefik_acme_email` | Email for Let's Encrypt certificates |
| `traefik_cf_dns_api_token` | Cloudflare API token for DNS challenges |

#### ddclient

| Variable | Description |
|----------|-------------|
| `ddclient_cloudflare_email` | Cloudflare account email |
| `ddclient_cloudflare_api_token` | Cloudflare API token for dynamic DNS updates |

#### PocketID

| Variable | Description |
|----------|-------------|
| `pocketid_encryption_key` | Encryption key |

#### TinyAuth

| Variable | Description |
|----------|-------------|
| `tinyauth_secret` | Session secret |
| `tinyauth_allowed_user` | Allowed username |
| `tinyauth_pocketid_client_secret` | PocketID OAuth client secret |
| `tinyauth_pocketid_token_url` | PocketID token endpoint URL |
| `tinyauth_pocketid_user_info_url` | PocketID user info endpoint URL |

#### Line (in-house)

[line](https://github.com/jedmund/line) is one of our own projects, built on the server from a clone of the repo (configured via `line_repo` / `line_version` in `roles/infra_gateway/defaults/main.yml`). The clone lives at `{{ docker_base_path }}/infra-gateway/source/line` and is refreshed on every deploy.

| Variable | Description |
|----------|-------------|
| `line_oidc_client_id` | OIDC client ID from PocketID |
| `line_oidc_client_secret` | OIDC client secret from PocketID |

Register the OIDC client manually in PocketID with redirect URI `https://atelier.house/auth/callback`, then drop the values into the vault.

### group_vars/media_acquisition/vault.yml

#### Gluetun

| Variable | Description |
|----------|-------------|
| `gluetun_openvpn_user` | VPN username |
| `gluetun_openvpn_password` | VPN password |

#### Unpackerr

| Variable | Description |
|----------|-------------|
| `unpackerr_sonarr_api_key` | Sonarr API key |
| `unpackerr_radarr_api_key` | Radarr API key |

### group_vars/media_consumption/vault.yml

#### Romm

| Variable | Description |
|----------|-------------|
| `romm_db_user` | MariaDB username |
| `romm_db_password` | MariaDB password |
| `romm_db_root_password` | MariaDB root password |
| `romm_auth_secret_key` | Authentication secret key |
| `romm_igdb_client_secret` | IGDB API client secret |
| `romm_oidc_client_secret` | OIDC client secret |
| `romm_steamgriddb_api_key` | SteamGridDB API key |
| `romm_mobygames_api_key` | MobyGames API key |
| `romm_screenscraper_user` | ScreenScraper username |
| `romm_screenscraper_password` | ScreenScraper password |
| `romm_retroachievements_api_key` | RetroAchievements API key |

### group_vars/immich/vault.yml

| Variable | Description |
|----------|-------------|
| `immich_db_password` | Immich PostgreSQL password |

### group_vars/papra/vault.yml

| Variable | Description |
|----------|-------------|
| `papra_auth_secret` | Papra authentication secret |
| `papra_oidc_client_id` | Papra OIDC client ID |
| `papra_oidc_client_secret` | Papra OIDC client secret |

### group_vars/homebox/vault.yml

| Variable | Description |
|----------|-------------|
| `homebox_oidc_client_id` | Homebox OIDC client ID |
| `homebox_oidc_client_secret` | Homebox OIDC client secret |

### group_vars/album_sort/vault.yml

[album-sort](https://github.com/jedmund/album-sort) is one of our own projects, built on the host from a GitLab clone (`album_sort_repo` in `roles/album_sort/defaults/main.yml`).

| Variable | Description |
|----------|-------------|
| `album_sort_apple_music_team_id` | Apple Music API team ID |
| `album_sort_apple_music_key_id` | Apple Music API key ID |
| `album_sort_apple_music_private_key` | Apple Music API private key |
| `album_sort_discogs_token` | Discogs API token |
| `album_sort_kagi_api_key` | Kagi API key |
| `album_sort_multi_scrobbler_token` | Shared token for Multi-Scrobbler integration |

### group_vars/dawarich/vault.yml

| Variable | Description |
|----------|-------------|
| `dawarich_db_password` | Dawarich PostgreSQL password |
| `dawarich_secret_key_base` | Rails secret key base |
| `dawarich_oidc_client_id` | Dawarich OIDC client ID |
| `dawarich_oidc_client_secret` | Dawarich OIDC client secret |

### group_vars/miniflux/vault.yml

| Variable | Description |
|----------|-------------|
| `miniflux_admin_password` | Admin password |
| `miniflux_db_password` | PostgreSQL password |
| `miniflux_oauth2_client_id` | Miniflux OIDC client ID |
| `miniflux_oauth2_client_secret` | Miniflux OIDC client secret |
| `fivefilters_admin_password` | FiveFilters admin password |

### group_vars/karakeep/vault.yml

| Variable | Description |
|----------|-------------|
| `karakeep_meili_master_key` | Meilisearch master key |
| `karakeep_nextauth_secret` | NextAuth session secret |
| `karakeep_oauth_client_id` | Karakeep OIDC client ID |
| `karakeep_oauth_client_secret` | Karakeep OIDC client secret |
| `karakeep_openai_api_key` | OpenAI API key (for AI features) |

### group_vars/blinko/vault.yml

| Variable | Description |
|----------|-------------|
| `blinko_db_password` | Blinko PostgreSQL password |
| `blinko_nextauth_secret` | Blinko NextAuth secret (optional) |

### group_vars/obsidian_livesync/vault.yml

| Variable | Description |
|----------|-------------|
| `obsidian_livesync_couchdb_user` | CouchDB admin user |
| `obsidian_livesync_couchdb_password` | CouchDB admin password |

### group_vars/n8n/vault.yml

| Variable | Description |
|----------|-------------|
| `n8n_db_password` | n8n PostgreSQL password |
| `n8n_encryption_key` | n8n encryption key (optional if already initialized without one) |

### group_vars/development/vault.yml

| Variable | Description |
|----------|-------------|
| `gitlab_initial_root_password` | GitLab initial root password (auto-generated if empty) |
| `gitlab_oidc_client_id` | GitLab OIDC client ID (PocketID) |
| `gitlab_oidc_client_secret` | GitLab OIDC client secret (PocketID) |
| `gitlab_runner_auth_token` | GitLab Runner auth token (nuc-mini-docker) |
| `gitlab_runner_macos_auth_token` | GitLab Runner auth token (mac-mini-xcode) |
| `renovate_gitlab_token` | Renovate bot GitLab personal access token |
| `renovate_github_token` | Renovate GitHub token (optional, for rate limits) |
| `open_webui_secret_key` | Open WebUI session secret |
| `open_webui_oauth_client_id` | Open WebUI OAuth client ID |
| `open_webui_oauth_client_secret` | Open WebUI OAuth client secret |

### group_vars/social/vault.yml

| Variable | Description |
|----------|-------------|
| `mastodon_db_password` | Mastodon PostgreSQL password |
| `mastodon_secret_key_base` | Rails secret key base |
| `mastodon_otp_secret` | OTP secret for 2FA |
| `mastodon_vapid_private_key` | VAPID private key for push notifications |
| `mastodon_vapid_public_key` | VAPID public key for push notifications |
| `mastodon_aws_access_key_id` | AWS access key for S3 |
| `mastodon_aws_secret_access_key` | AWS secret key for S3 |
| `mastodon_active_record_encryption_deterministic_key` | Active Record encryption key |
| `mastodon_active_record_encryption_key_derivation_salt` | Active Record key derivation salt |
| `mastodon_active_record_encryption_primary_key` | Active Record primary key |

## Usage

Run `make help` to see all available commands. Common operations:

### Deployment

```bash
# Deploy everything
make deploy-all

# Deploy specific stacks
make deploy-infra-core
make deploy-infra-gateway
make deploy-media-acquisition
make deploy-media-consumption
make deploy-immich
make deploy-miniflux
make deploy-karakeep
make deploy-blinko
make deploy-obsidian-livesync
make deploy-n8n
make deploy-changedetection
make deploy-copyparty

# One-time migration from old content/reading stacks to product stacks
bin/split-content-reading-product-vaults
make deploy-migrate-content-reading-products

# After verifying product stacks and backups, archive old runtime dirs
make archive-legacy-content-reading-stacks

# One-time migration from productivity to product stacks
# This removes empty Draftboard and SilverBullet runtime data.
bin/split-productivity-product-vaults
make deploy-migrate-productivity-products

# One-time migration from utilities to product stacks
bin/split-utilities-product-vaults
make deploy-migrate-utilities-products

# Deploy prerequisites only (Docker, networks, volumes)
make deploy-prerequisites

# Dry-run before deploying
make dry-run
```

### Targeting Specific Hosts or Services

```bash
# Deploy to a specific host
make deploy-limit HOST=mini

# Deploy specific services by tag
make deploy-tags TAGS=traefik,plex

# Skip specific services
make deploy-skip-tags TAGS=flood
```

### Vault Management

```bash
# Edit a vault file
make edit-vault FILE=group_vars/infra_core/vault.yml

# View vault contents
make view-vault FILE=group_vars/infra_core/vault.yml

# Encrypt a new file
make encrypt FILE=group_vars/new_stack/vault.yml

# Decrypt a file for manual editing
make decrypt FILE=group_vars/infra_core/vault.yml
```

### Validation

```bash
# Check syntax of all playbooks
make syntax

# Lint playbooks
make lint

# Run all checks
make check
```

### Information

```bash
# List all hosts
make list-hosts

# List available tags
make list-tags

# Show variables for a host
make show-vars HOST=mini
```

### Docker Management

```bash
# Show running containers on all hosts
make docker-ps

# View container logs
make docker-logs HOST=mini CONTAINER=traefik

# Prune unused resources
make docker-prune
```

## Database Backups

Services using PostgreSQL store metadata in Docker volumes. To migrate to a new machine or create backups, use `pg_dump`.

### PostgreSQL Services

| Service | Container | Database | User |
|---------|-----------|----------|------|
| Miniflux | `miniflux-db` | `miniflux` | `miniflux` |
| Immich | `immich-database` | `immich` | `postgres` |
| Dawarich | `dawarich_postgres` | `dawarich_production` | `dawarich` |
| n8n | `n8n_postgres` | `n8n` | `n8n` |
| Blinko | `blinko_postgres` | `blinko` | `blinko` |
| Mastodon | `mastodon-db` | `mastodon_production` | `mastodon` |

GitLab is not in this table because GitLab Omnibus runs its own embedded PostgreSQL and uses its own backup tooling (`gitlab-backup create`). A nightly application-consistent dump is already scheduled in `roles/development/tasks/main.yml`.

### Backup (pg_dump)

```bash
# Generic format
docker exec <container> pg_dump -U <user> <database> > backup.sql

# Examples
docker exec miniflux-db pg_dump -U miniflux miniflux > miniflux_backup.sql
docker exec immich-database pg_dump -U postgres immich > immich_backup.sql
docker exec dawarich_postgres pg_dump -U dawarich dawarich_production > dawarich_backup.sql
docker exec n8n_postgres pg_dump -U n8n n8n > n8n_backup.sql
docker exec blinko_postgres pg_dump -U blinko blinko > blinko_backup.sql
docker exec mastodon-db pg_dump -U mastodon mastodon_production > mastodon_backup.sql
```

### Restore (pg_restore)

```bash
# Stop the application container first
docker stop <app-container>

# Restore the backup
docker exec -i <container> psql -U <user> <database> < backup.sql

# Restart the application
docker start <app-container>
```

### MariaDB Services

| Service | Container | Database | User |
|---------|-----------|----------|------|
| Romm | `romm-db` | `romm` | `romm-atelier` |

```bash
# Backup
docker exec romm-db mariadb-dump -u romm-atelier -p<password> romm > romm_backup.sql

# Restore
docker exec -i romm-db mariadb -u romm-atelier -p<password> romm < romm_backup.sql
```

### Migration to New Machine

1. **Backup on old machine:**
   ```bash
   docker exec immich-database pg_dump -U postgres immich > immich_backup.sql
   scp immich_backup.sql newmachine:/tmp/
   ```

2. **Deploy stack on new machine** (creates fresh volumes):
   ```bash
   ansible-playbook deploy/immich.yml
   ```

3. **Restore on new machine:**
   ```bash
   docker stop immich-server
   docker exec -i immich-database psql -U postgres immich < /tmp/immich_backup.sql
   docker start immich-server
   ```
