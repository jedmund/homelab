# Homelab

Ansible playbooks for deploying and managing a homelab infrastructure.

## Structure

```
.
├── deploy/               # Stack deployment playbooks
│   ├── all.yml
│   ├── prerequisites.yml
│   ├── infra_core.yml
│   ├── infra_gateway.yml
│   ├── media_acquisition.yml
│   ├── media_consumption.yml
│   ├── content_management.yml
│   ├── development.yml
│   └── productivity.yml
├── group_vars/           # Host group variables and vault files
├── inventory/            # Host inventory
├── roles/                # Ansible roles
│   ├── docker/           # Docker installation and configuration
│   ├── docker-volumes/   # Persistent volume management
│   ├── firewall/         # UFW firewall rules
│   ├── networks/         # Docker network configuration
│   ├── infra_core/       # Komodo deployment platform
│   ├── infra_gateway/    # Traefik, AdGuard, Glance, PocketID
│   ├── media_acquisition/# Sonarr, Radarr, Prowlarr, Flood, Gluetun
│   ├── media_consumption/# Plex, Miniflux, Kavita, Romm
│   ├── content_management/ # Immich, Papra, SongKong
│   ├── development/      # Forgejo, n8n, Open WebUI
│   └── productivity/     # Strudel, Silverbullet, Blinko
└── Makefile              # Deployment commands
```

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

#### Miniflux

| Variable | Description |
|----------|-------------|
| `miniflux_admin_username` | Admin username |
| `miniflux_admin_password` | Admin password |
| `miniflux_db_user` | PostgreSQL username |
| `miniflux_db_password` | PostgreSQL password |

#### Karakeep

| Variable | Description |
|----------|-------------|
| `karakeep_meili_master_key` | Meilisearch master key |
| `karakeep_nextauth_secret` | NextAuth session secret |
| `karakeep_openai_api_key` | OpenAI API key (for AI features) |
| `karakeep_oauth_client_secret` | OAuth client secret |

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
| Forgejo | `forgejo-db` | `forgejo` | `forgejo` |
| n8n | `n8n-db` | `n8n` | `n8n` |
| Blinko | `blinko-db` | `blinko` | `blinko` |

### Backup (pg_dump)

```bash
# Generic format
docker exec <container> pg_dump -U <user> <database> > backup.sql

# Examples
docker exec miniflux-db pg_dump -U miniflux miniflux > miniflux_backup.sql
docker exec immich-database pg_dump -U postgres immich > immich_backup.sql
docker exec forgejo-db pg_dump -U forgejo forgejo > forgejo_backup.sql
docker exec n8n-db pg_dump -U n8n n8n > n8n_backup.sql
docker exec blinko-db pg_dump -U blinko blinko > blinko_backup.sql
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
   ansible-playbook deploy/content_management.yml
   ```

3. **Restore on new machine:**
   ```bash
   docker stop immich-server
   docker exec -i immich-database psql -U postgres immich < /tmp/immich_backup.sql
   docker start immich-server
   ```
