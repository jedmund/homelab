# Secrets

Vault files are local configuration. Git ignores `**/vault.yml`; a clone does
not contain the credentials needed to deploy an existing installation.

## File placement

Store shared host credentials in `group_vars/compute_servers/vault.yml` and
service credentials in `group_vars/<inventory-group>/vault.yml`.
The group must exist in [inventory](../inventory/hosts.yml), and the target
host must belong to it. Use the inventory group, which can differ from the
role name: Beszel agents use `group_vars/beszel_agents/vault.yml`.

Ansible combines variables from all groups assigned to a host. Group vaults
are an organizational boundary, not isolated credential stores. For example,
the backup role reads database credentials from other groups on `nuc-mini`.
Avoid defining different values for the same variable in overlapping groups.

The gateway has separate groups and vaults for `traefik`, `pocketid`,
`tinyauth`, `line`, and `ddclient`. There is no current `infra_gateway` group.
OpenSpeedTest has no secret inputs in its current role.

## Create and edit

After configuring the password file with `make setup`, create a new vault:

```sh
mkdir -p group_vars/traefik
ansible-vault create group_vars/traefik/vault.yml
```

Edit an existing vault:

```sh
make edit-vault FILE=group_vars/traefik/vault.yml
```

`edit-vault` does not create a missing file. The default password path is
`~/.ansible-vault-pass`, configured in `ansible.cfg`. Preserve both the encrypted
vaults and their recovery credentials outside this checkout.

Use the exact variable names expected by the role. A `vault_` input often maps
to a differently named runtime variable in defaults. Do not rotate persistent
application encryption keys as part of routine deployment or image updates.

## Service inputs

The tables below cover common deployment inputs. The role's defaults,
assertions, and templates define the complete set and whether each value is
required. A `default('')` expression does not by itself make a value optional.
Service runbooks contain callbacks and first-deployment ordering where needed.

### group_vars/compute_servers/vault.yml

Shared secrets used by multiple stacks.

| Variable | Description |
| --- | --- |
| `sendgrid_api_key` | SendGrid SMTP API key (used by Mastodon, Dawarich, and Kaneo) |
| `gitlab_cache_s3_access_key_id` | GitLab CI cache Garage S3 access key (shared by the nuc-mini and max runners) |
| `gitlab_cache_s3_secret_access_key` | GitLab CI cache Garage S3 secret key |

### group_vars/degoog/vault.yml

| Variable | Description |
| --- | --- |
| `vault_degoog_settings_password` | Degoog settings password; required to manage engines and extensions |

### group_vars/album_sort/vault.yml

Album Sort pulls CI-built images. Deployment, proxy trust, and encryption-key
requirements are documented in the [role runbook](../roles/album_sort/README.md).

| Variable | Description |
| --- | --- |
| `album_sort_apple_music_team_id` | Apple Music API team ID |
| `album_sort_apple_music_key_id` | Apple Music API key ID |
| `album_sort_apple_music_private_key` | Apple Music API private key |
| `album_sort_discogs_token` | Discogs API token |
| `album_sort_kagi_api_key` | Kagi API key |
| `vault_album_sort_registry_username` | GitLab deploy-token username with `read_registry` access |
| `vault_album_sort_registry_password` | GitLab deploy-token password |
| `vault_album_sort_oidc_client_id` | PocketID client ID |
| `vault_album_sort_oidc_client_secret` | PocketID client secret |
| `vault_album_sort_user_secret_encryption_key` | Persistent canonical base64 of 32 random bytes; preserve across deployments |

### group_vars/aurral/vault.yml

Aurral is deployed at `https://aurral.atelier.house` with native PocketID
OIDC. See the [Aurral deployment runbook](../roles/aurral/README.md) for its
first-run order, storage paths, and integration checks.

| Variable | Description |
| --- | --- |
| `vault_aurral_oidc_client_id` | PocketID confidential-client ID |
| `vault_aurral_oidc_client_secret` | PocketID confidential-client secret |
| `vault_aurral_oidc_admin_users` | YAML list of PocketID `preferred_username` values promoted to Aurral admin |

Register this exact PocketID callback before deploying:
`https://aurral.atelier.house/sso/callback`.

### group_vars/backup/vault.yml

| Variable | Description |
| --- | --- |
| `borg_passphrase` | Passphrase for the Borg repository |
| `borg_healthchecks_url` | Monitoring ping URL |

Keep a recovery copy of the passphrase outside the repository and backup
host. Other database credentials come from the application groups assigned
to `nuc-mini`. See [Backup](../roles/backup/README.md).

### group_vars/beszel_agents/vault.yml

Deploy the hub before the agents. Configure its PocketID provider in the
application with callback `https://beszel.atelier.house/api/oauth2-redirect`.
The role does not provision the provider; `beszel_disable_password_auth`
defaults to true, so verify that the login method is configured for the
installation.

Create or enable a permanent universal token under `/settings/tokens` in the
hub. Obtain the public key from its generated agent command, store both values
below, then run `make deploy-beszel-agents`.

| Variable | Description |
| --- | --- |
| `vault_beszel_agent_key` | Hub public key from Beszel's generated agent command |
| `vault_beszel_agent_token` | Permanent universal token for agent WebSocket registration |

### group_vars/dawarich/vault.yml

| Variable | Description |
| --- | --- |
| `dawarich_db_password` | Dawarich PostgreSQL password |
| `dawarich_secret_key_base` | Rails secret key base |
| `dawarich_oidc_client_id` | Dawarich OIDC client ID |
| `dawarich_oidc_client_secret` | Dawarich OIDC client secret |

### group_vars/ddclient/vault.yml

| Variable | Description |
| --- | --- |
| `ddclient_cloudflare_email` | Cloudflare account email |
| `ddclient_cloudflare_api_token` | Cloudflare Global API Key used with the account email; the variable name is historical |

### group_vars/development_linux/vault.yml

| Variable | Description |
| --- | --- |
| `gitlab_runner_linux_auth_token` | GitLab Runner auth token (max-docker) |

### group_vars/development_macos/vault.yml

| Variable | Description |
| --- | --- |
| `gitlab_runner_macos_auth_token` | GitLab Runner auth token (mac-mini-xcode) |

### group_vars/gitlab/vault.yml

| Variable | Description |
| --- | --- |
| `gitlab_initial_root_password` | GitLab initial root password (auto-generated if empty) |
| `gitlab_oidc_client_id` | GitLab OIDC client ID (PocketID) |
| `gitlab_oidc_client_secret` | GitLab OIDC client secret (PocketID) |
| `gitlab_runner_auth_token` | GitLab Runner auth token (nuc-mini-docker) |
| `gitlab_cache_garage_rpc_secret` | CI cache Garage RPC secret (nuc-mini only) |
| `gitlab_cache_garage_admin_token` | CI cache Garage admin API token (nuc-mini only) |
| `renovate_gitlab_token` | Renovate bot GitLab personal access token |
| `renovate_github_token` | Renovate GitHub token (optional, for rate limits) |

After the first GitLab deployment, run the staged
`/opt/docker/gitlab/ci_cache_bootstrap.sh` on `nuc-mini` to initialize Garage's
layout and `ci-cache` bucket. Follow the script's credential instructions;
store the shared S3 access key and secret in the `compute_servers` vault.
The script source is [ci_cache_bootstrap.sh](../roles/gitlab/files/ci_cache_bootstrap.sh).

Without a configured access key, the runners use local caches. The role sets
an object-expiry lifecycle using `gitlab_cache_s3_expiry_days` (default 14).

### group_vars/gluetun/vault.yml

| Variable | Description |
| --- | --- |
| `gluetun_vpn_provider` | VPN provider |
| `gluetun_vpn_type` | VPN type (`openvpn` or `wireguard`) |
| `gluetun_openvpn_user` | OpenVPN username |
| `gluetun_openvpn_password` | OpenVPN password |
| `gluetun_wireguard_private_key` | WireGuard private key |
| `gluetun_wireguard_addresses` | WireGuard address list |
| `gluetun_server_countries` | Optional server country filter |

### group_vars/homebox/vault.yml

| Variable | Description |
| --- | --- |
| `homebox_oidc_client_id` | Homebox OIDC client ID |
| `homebox_oidc_client_secret` | Homebox OIDC client secret |

### group_vars/hugginghack/vault.yml

Use the [HuggingHack runbook](../roles/hugginghack/README.md) for PostgreSQL,
PocketID, and optional Hugging Face credentials, callbacks, and storage setup.

### group_vars/immich/vault.yml

| Variable | Description |
| --- | --- |
| `immich_db_password` | Immich PostgreSQL password |

### group_vars/infra_core/vault.yml

| Variable | Description |
| --- | --- |
| `komodo_db_username` | MongoDB username |
| `komodo_db_password` | MongoDB password |
| `komodo_init_admin_username` | Initial admin username |
| `komodo_init_admin_password` | Initial admin password |
| `komodo_jwt_secret` | JWT signing secret |
| `komodo_passkey` | Passkey for periphery authentication |
| `komodo_webhook_secret` | Webhook signing secret |
| `komodo_oidc_client_secret` | OIDC client secret (if using SSO) |

### group_vars/infra_periphery/vault.yml

| Variable | Description |
| --- | --- |
| `komodo_passkey` | Periphery auth passkey (must equal infra_core's `komodo_passkey`) |

### group_vars/kaneo/vault.yml

Use the complete schema in the [Kaneo runbook](../roles/kaneo/README.md).
It covers PostgreSQL, Redis, session and SCM encryption keys, registry access,
PocketID, GitHub App, GitLab OAuth, and Garage credentials. Garage access keys
are provisioned after its initial deployment.

### group_vars/karakeep/vault.yml

| Variable | Description |
| --- | --- |
| `karakeep_meili_master_key` | Meilisearch master key |
| `karakeep_nextauth_secret` | NextAuth session secret |
| `karakeep_oauth_client_id` | Karakeep OIDC client ID |
| `karakeep_oauth_client_secret` | Karakeep OIDC client secret |
| `karakeep_openai_api_key` | OpenAI API key (for AI features) |

### group_vars/kibble/vault.yml

Kibble retains `vault_feederhub_*` input names. See the
[Kibble runbook](../roles/kibble/README.md) and
[defaults](../roles/kibble/defaults/main.yml) for registry, feeder, and optional
Garage credentials.

### group_vars/kizuna/vault.yml

Use the [Kizuna runbook](../roles/kizuna/README.md) and
[role defaults](../roles/kizuna/defaults/main.yml) for registry, PostgreSQL,
Rails encryption, PocketID, Garage, and optional integration credentials.
Preserve existing encryption keys when redeploying.

### group_vars/line/vault.yml

Line is built from the checkout configured by
[roles/line/defaults/main.yml](../roles/line/defaults/main.yml).
Its default PocketID callback is `https://atelier.house/auth/callback`.

| Variable | Description |
| --- | --- |
| `vault_line_admin_emails` | Comma-separated administrator email addresses |
| `line_oidc_client_id` | PocketID client ID |
| `line_oidc_client_secret` | PocketID client secret |
| `line_widget_token_key` | Optional widget-token key; the application falls back to the OIDC client secret |
| `line_reddit_client_id` | Optional Reddit integration |
| `line_twitch_client_id`, `line_twitch_client_secret` | Optional Twitch integration |
| `line_youtube_api_key` | Optional YouTube integration |
| `line_bart_api_key`, `line_bay_511_api_key` | Optional transit integrations |
| `line_github_oauth_client_id`, `line_github_oauth_client_secret` | Optional GitHub integration |

### group_vars/matrix/vault.yml

The Matrix stack renders Synapse, MAS, PostgreSQL, TURN, and LiveKit settings.
Use the secret references in [defaults](../roles/matrix/defaults/main.yml) and
[templates](../roles/matrix/templates/) for the complete set. This includes
`synapse_db_password` and `mas_db_password`, also used by the backup role.

### group_vars/miniflux/vault.yml

| Variable | Description |
| --- | --- |
| `miniflux_admin_password` | Admin password |
| `miniflux_db_password` | PostgreSQL password |
| `miniflux_oauth2_client_id` | Miniflux OIDC client ID |
| `miniflux_oauth2_client_secret` | Miniflux OIDC client secret |
| `fivefilters_admin_password` | FiveFilters admin password |

### group_vars/musicbrainz/vault.yml

| Variable | Description |
| --- | --- |
| `musicbrainz_replication_token` | MetaBrainz access token for the live replication feed |
| `musicbrainz_healthchecks_url` | Dedicated Healthchecks.io ping URL for the daily replication job |

Configure the Healthchecks check for `0 3 * * *` UTC with six hours of grace.
The role requires both values and renders them as `0600` Docker secret files.
See the [MusicBrainz runbook](../roles/musicbrainz/README.md).

### group_vars/multi_scrobbler/vault.yml

| Variable | Description |
| --- | --- |
| `multi_scrobbler_lze_token` | ListenBrainz token for Album Sort |
| `multi_scrobbler_plex_token` | Plex token |
| `multi_scrobbler_lastfm_api_key` | Last.fm API key |
| `multi_scrobbler_lastfm_api_secret` | Last.fm API secret |
| `multi_scrobbler_mb_contact` | MusicBrainz contact string |

### group_vars/n8n/vault.yml

| Variable | Description |
| --- | --- |
| `n8n_db_password` | n8n PostgreSQL password |
| `n8n_encryption_key` | n8n encryption key (optional if already initialized without one) |
| `n8n_instance_ai_model_api_key` | Open WebUI API key for the "n8n Assistant" user; the model the Assistant runs on |
| `n8n_sandbox_api_key` | How n8n authenticates to the sandbox API |
| `n8n_sandbox_runner_api_key` | How the sandbox API authenticates to the sandbox runner |
| `n8n_sandbox_registration_token` | Shared secret the sandbox runner registers with |

Generate the three `n8n_sandbox_*` values independently, for example with
`openssl rand -hex 32`. Redeploy the stack after changing them so the API,
runner, and n8n receive matching configuration.

### group_vars/obsidian_livesync/vault.yml

| Variable | Description |
| --- | --- |
| `obsidian_livesync_couchdb_user` | CouchDB admin user |
| `obsidian_livesync_couchdb_password` | CouchDB admin password |

### group_vars/open_webui/vault.yml

| Variable | Description |
| --- | --- |
| `open_webui_secret_key` | Open WebUI session secret |
| `open_webui_oauth_client_id` | Open WebUI OAuth client ID |
| `open_webui_oauth_client_secret` | Open WebUI OAuth client secret |

### group_vars/papra/vault.yml

| Variable | Description |
| --- | --- |
| `papra_auth_secret` | Papra authentication secret |
| `papra_oidc_client_id` | Papra OIDC client ID |
| `papra_oidc_client_secret` | Papra OIDC client secret |

### group_vars/plex/vault.yml

| Variable | Description |
| --- | --- |
| `plex_claim` | Plex claim token (optional, usually only needed for first bootstrap) |

### group_vars/pocketid/vault.yml

| Variable | Description |
| --- | --- |
| `pocketid_encryption_key` | Encryption key |

### group_vars/qui/vault.yml

| Variable | Description |
| --- | --- |
| `qui_oidc_client_id` | OIDC client ID |
| `qui_oidc_client_secret` | OIDC client secret |

### group_vars/romm/vault.yml

| Variable | Description |
| --- | --- |
| `romm_db_password` | MariaDB password |
| `romm_db_root_password` | MariaDB root password |
| `romm_auth_secret_key` | Authentication secret key |
| `romm_oidc_client_id` | OIDC client ID |
| `romm_oidc_client_secret` | OIDC client secret |
| `romm_db_user` | MariaDB username (optional override) |
| `romm_igdb_client_id` | IGDB API client ID (optional) |
| `romm_igdb_client_secret` | IGDB API client secret |
| `romm_steamgriddb_api_key` | SteamGridDB API key |
| `romm_mobygames_api_key` | MobyGames API key |
| `romm_screenscraper_user` | ScreenScraper username |
| `romm_screenscraper_password` | ScreenScraper password |
| `romm_retroachievements_api_key` | RetroAchievements API key |

### group_vars/slskd/vault.yml

| Variable | Description |
| --- | --- |
| `slskd_slsk_username` | Soulseek username |
| `slskd_slsk_password` | Soulseek password |
| `slskd_web_username` | slskd web UI username |
| `slskd_web_password` | slskd web UI password |

### group_vars/social/vault.yml

| Variable | Description |
| --- | --- |
| `mastodon_db_password` | Mastodon PostgreSQL password |
| `mastodon_secret_key_base` | Rails secret key base |
| `mastodon_otp_secret` | OTP secret for 2FA |
| `mastodon_active_record_encryption_deterministic_key` | Persistent Active Record encryption key; preserve across deployments |
| `mastodon_active_record_encryption_key_derivation_salt` | Persistent Active Record key derivation salt; preserve across deployments |
| `mastodon_active_record_encryption_primary_key` | Persistent Active Record primary key; preserve across deployments |
| `mastodon_vapid_private_key` | VAPID private key for push notifications |
| `mastodon_vapid_public_key` | VAPID public key for push notifications |
| `mastodon_aws_access_key_id` | AWS access key for S3 |
| `mastodon_aws_secret_access_key` | AWS secret key for S3 |
### group_vars/tinyauth/vault.yml

| Variable | Description |
| --- | --- |
| `tinyauth_secret` | Session secret |
| `vault_tinyauth_allowed_user` | Primary administrator email |
| `vault_tinyauth_atelier_users` | Comma-separated email list for routes using the shared allowlist |
| `tinyauth_pocketid_client_id` | PocketID OAuth client ID |
| `tinyauth_pocketid_client_secret` | PocketID OAuth client secret |

### group_vars/traefik/vault.yml

| Variable | Description |
| --- | --- |
| `traefik_acme_email` | Email for Let's Encrypt certificates |
| `traefik_cf_dns_api_token` | Cloudflare API token for DNS challenges |

### group_vars/unpackerr/vault.yml

| Variable | Description |
| --- | --- |
| `unpackerr_sonarr_api_key` | Sonarr API key |
| `unpackerr_radarr_api_key` | Radarr API key |
| `unpackerr_lidarr_api_key` | Lidarr API key |
