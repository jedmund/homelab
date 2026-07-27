# Vault variables

Secrets are stored in encrypted `group_vars/<group>/vault.yml` files. Vault
files are intentionally not committed; role defaults and templates reference
the variable names that an operator must provide.

## Workflow

Create or edit a vault with the Make targets:

```sh
make edit-vault FILE=group_vars/infra_core/vault.yml
make view-vault FILE=group_vars/infra_core/vault.yml
make encrypt FILE=group_vars/new_stack/vault.yml
make rekey-vault FILE=group_vars/infra_core/vault.yml
```

Use the same variable names shown below. Never put secret values in role
defaults, inventory, templates, examples, or documentation.

This index covers the repository's vault-backed inputs. A linked role README
is authoritative when a service needs generation, registration, or bootstrap
steps in addition to the variable names.

## Shared and host-level vaults

### `group_vars/compute_servers/vault.yml`

| Variable | Purpose |
| --- | --- |
| `sendgrid_api_key` | Shared SendGrid SMTP credential |
| `gitlab_cache_s3_access_key_id` | Shared GitLab CI cache Garage access key |
| `gitlab_cache_s3_secret_access_key` | Shared GitLab CI cache Garage secret key |
| `vault_netdata_stream_api_key` | Netdata parent/child streaming key |

See the [Netdata role](../roles/monitoring/README.md) for key generation and
topology details.

### `group_vars/agents_linux/vault.yml`

| Variable | Purpose |
| --- | --- |
| `atelier_vllm_api_key` | API key used by Pi and OpenCode for the Atelier vLLM endpoint |

### Runner vaults

| File | Variable | Purpose |
| --- | --- | --- |
| `group_vars/development_linux/vault.yml` | `gitlab_runner_linux_auth_token` | `max-docker` runner token |
| `group_vars/development_macos/vault.yml` | `gitlab_runner_macos_auth_token` | `mac-mini-xcode` runner token |

## Infrastructure vaults

### `group_vars/infra_core/vault.yml`

| Variable | Purpose |
| --- | --- |
| `komodo_db_username` | Komodo MongoDB username |
| `komodo_db_password` | Komodo MongoDB password |
| `komodo_init_admin_username` | Initial Komodo administrator |
| `komodo_init_admin_password` | Initial Komodo administrator password |
| `komodo_jwt_secret` | Komodo JWT signing secret |
| `komodo_passkey` | Core/Periphery authentication passkey |
| `komodo_webhook_secret` | Webhook signing secret |
| `komodo_oidc_client_secret` | Optional OIDC client secret |

### `group_vars/infra_periphery/vault.yml`

| Variable | Purpose |
| --- | --- |
| `komodo_passkey` | Must match `infra_core`'s `komodo_passkey` |

See the [Periphery role](../roles/infra_periphery/README.md).

### `group_vars/infra_gateway/vault.yml`

| Service | Variables |
| --- | --- |
| Traefik | `traefik_acme_email`, `traefik_cf_dns_api_token` |
| ddclient | `ddclient_cloudflare_email`, `ddclient_cloudflare_api_token` |
| PocketID | `pocketid_encryption_key` |
| TinyAuth | `tinyauth_secret`, `vault_tinyauth_allowed_user`, `vault_tinyauth_atelier_users`, `tinyauth_pocketid_client_id`, `tinyauth_pocketid_client_secret`, `tinyauth_pocketid_token_url`, `tinyauth_pocketid_user_info_url` |
| Line | `vault_line_admin_emails`, `line_oidc_client_id`, `line_oidc_client_secret` |
| Optional Line integrations | `line_widget_token_key`, `line_reddit_client_id`, `line_twitch_client_id`, `line_twitch_client_secret`, `line_youtube_api_key`, `line_bart_api_key`, `line_bay_511_api_key`, `line_github_oauth_client_id`, `line_github_oauth_client_secret` |

The [gateway role](../roles/infra_gateway/README.md) documents Line's
build-on-host exception and PocketID registration.

### `group_vars/dokploy/vault.yml`

| Variable | Purpose |
| --- | --- |
| `dokploy_cloudflare_token` | Cloudflare token with DNS edit access |
| `dokploy_acme_email` | Let's Encrypt registration email |

See the [Dokploy role](../roles/dokploy/README.md) for one-time UI setup.

### `group_vars/frp/vault.yml`

| Variable | Purpose |
| --- | --- |
| `vault_frp_token` | frp client/server authentication token |
| `vault_frp_dashboard_password` | frps dashboard password |

See the [frp role](../roles/frp/README.md).

### `group_vars/beszel_agents/vault.yml`

| Variable | Purpose |
| --- | --- |
| `vault_beszel_agent_key` | Hub public key from Beszel's generated agent command |
| `vault_beszel_agent_token` | Permanent universal agent registration token |

Follow the [Beszel bootstrap guide](../roles/beszel/README.md) before deploying
agents.

## Media vaults

### `group_vars/gluetun/vault.yml`

| Variable | Purpose |
| --- | --- |
| `gluetun_vpn_provider` | VPN provider |
| `gluetun_vpn_type` | `openvpn` or `wireguard` |
| `gluetun_openvpn_user` | OpenVPN username |
| `gluetun_openvpn_password` | OpenVPN password |
| `gluetun_wireguard_private_key` | WireGuard private key |
| `gluetun_wireguard_addresses` | WireGuard address list |
| `gluetun_server_countries` | Optional server country filter |

### `group_vars/unpackerr/vault.yml`

| Variable | Purpose |
| --- | --- |
| `unpackerr_sonarr_api_key` | Sonarr API key |
| `unpackerr_radarr_api_key` | Radarr API key |
| `unpackerr_lidarr_api_key` | Lidarr API key |

### `group_vars/slskd/vault.yml`

| Variable | Purpose |
| --- | --- |
| `slskd_slsk_username` | Soulseek username |
| `slskd_slsk_password` | Soulseek password |
| `slskd_web_username` | Web UI username |
| `slskd_web_password` | Web UI password |

### `group_vars/qui/vault.yml`

| Variable | Purpose |
| --- | --- |
| `qui_oidc_client_id` | OIDC client ID |
| `qui_oidc_client_secret` | OIDC client secret |

### `group_vars/romm/vault.yml`

| Variable | Purpose |
| --- | --- |
| `romm_db_user` | Optional MariaDB username override |
| `romm_db_password` | MariaDB password |
| `romm_db_root_password` | MariaDB root password |
| `romm_auth_secret_key` | Authentication secret |
| `romm_oidc_client_id` | OIDC client ID |
| `romm_oidc_client_secret` | OIDC client secret |
| `romm_igdb_client_id` | Optional IGDB client ID |
| `romm_igdb_client_secret` | Optional IGDB client secret |
| `romm_steamgriddb_api_key` | SteamGridDB API key |
| `romm_mobygames_api_key` | MobyGames API key |
| `romm_screenscraper_user` | ScreenScraper username |
| `romm_screenscraper_password` | ScreenScraper password |
| `romm_retroachievements_api_key` | RetroAchievements API key |

### `group_vars/multi_scrobbler/vault.yml`

| Variable | Purpose |
| --- | --- |
| `multi_scrobbler_lze_token` | ListenBrainz token used by Album Sort |
| `multi_scrobbler_plex_token` | Plex token |
| `multi_scrobbler_lastfm_api_key` | Last.fm API key |
| `multi_scrobbler_lastfm_api_secret` | Last.fm API secret |
| `multi_scrobbler_mb_contact` | MusicBrainz contact string |

### Other media vaults

| File | Variables |
| --- | --- |
| `group_vars/plex/vault.yml` | `plex_claim` (optional first-bootstrap token) |
| `group_vars/musicbrainz/vault.yml` | `musicbrainz_replication_token`; see the [role README](../roles/musicbrainz/README.md) |

## Product and utility vaults

### Application databases and authentication

| File | Variables |
| --- | --- |
| `group_vars/immich/vault.yml` | `immich_db_password` |
| `group_vars/papra/vault.yml` | `papra_auth_secret`, `papra_oidc_client_id`, `papra_oidc_client_secret` |
| `group_vars/homebox/vault.yml` | `homebox_oidc_client_id`, `homebox_oidc_client_secret` |
| `group_vars/dawarich/vault.yml` | `dawarich_db_password`, `dawarich_secret_key_base`, `dawarich_oidc_client_id`, `dawarich_oidc_client_secret` |
| `group_vars/miniflux/vault.yml` | `miniflux_admin_password`, `miniflux_db_password`, `miniflux_oauth2_client_id`, `miniflux_oauth2_client_secret`, `fivefilters_admin_password` |
| `group_vars/karakeep/vault.yml` | `karakeep_meili_master_key`, `karakeep_nextauth_secret`, `karakeep_oauth_client_id`, `karakeep_oauth_client_secret`, `karakeep_openai_api_key` |
| `group_vars/blinko/vault.yml` | `blinko_db_password`, optional `blinko_nextauth_secret` |
| `group_vars/obsidian_livesync/vault.yml` | `obsidian_livesync_couchdb_user`, `obsidian_livesync_couchdb_password` |
| `group_vars/n8n/vault.yml` | `n8n_db_password`, optional `n8n_encryption_key` |

### `group_vars/album_sort/vault.yml`

| Variable | Purpose |
| --- | --- |
| `album_sort_apple_music_team_id` | Apple Music API team ID |
| `album_sort_apple_music_key_id` | Apple Music API key ID |
| `album_sort_apple_music_private_key` | Apple Music API private key |
| `album_sort_discogs_token` | Discogs API token |
| `album_sort_kagi_api_key` | Kagi API key |
| `album_sort_multi_scrobbler_token` | Multi-Scrobbler integration token |
| `vault_album_sort_registry_username` | GitLab registry deploy-token username |
| `vault_album_sort_registry_password` | GitLab registry deploy-token password |
| `vault_album_sort_oidc_client_id` | PocketID client ID |
| `vault_album_sort_oidc_client_secret` | PocketID client secret |

### `group_vars/hugginghack/vault.yml`

| Variable | Purpose |
| --- | --- |
| `vault_hugginghack_hf_token` | Optional read-only token for private or gated Hugging Face models |

See the [HuggingHack role](../roles/hugginghack/README.md) for storage setup.

### `group_vars/kibble/vault.yml`

Kibble's vault contains registry, Garage, OIDC, feeder, TUTK, and ONVIF
credentials. The complete example and bootstrap order live in the
[Kibble role README](../roles/kibble/README.md).

### `group_vars/kizuna/vault.yml`

Kizuna's vault contains registry, PostgreSQL, Garage, Rails, Active Record
encryption, OIDC, YouTube, screenshotter, and SearXNG credentials. See the
[Kizuna production runbook](../roles/kizuna/README.md). Treat the Active
Record encryption values as durable data-encryption keys, not rotatable
application tokens.

### `group_vars/vane/vault.yml`

| Variable | Purpose |
| --- | --- |
| `vault_vane_registry_username` | GitLab registry deploy-token username |
| `vault_vane_registry_password` | GitLab registry deploy-token password |
| `vault_vane_oidc_client_id` | PocketID client ID |
| `vault_vane_oidc_client_secret` | PocketID client secret |
| `vault_vane_session_secret` | Session signing secret, at least 32 characters |

See the [Vane role](../roles/vane/README.md).

## Development vaults

### `group_vars/gitlab/vault.yml`

| Variable | Purpose |
| --- | --- |
| `gitlab_initial_root_password` | Initial administrator password |
| `gitlab_oidc_client_id` | PocketID client ID |
| `gitlab_oidc_client_secret` | PocketID client secret |
| `gitlab_runner_auth_token` | `nuc-mini-docker` runner token |
| `gitlab_cache_garage_rpc_secret` | CI cache Garage RPC secret |
| `gitlab_cache_garage_admin_token` | CI cache Garage admin API token |
| `renovate_gitlab_token` | Renovate GitLab token |
| `renovate_github_token` | Optional GitHub token for higher rate limits |

The cache's S3 client keys live in the shared `compute_servers` vault. Follow
the [GitLab role README](../roles/gitlab/README.md) for the one-time Garage
bootstrap.

### `group_vars/open_webui/vault.yml`

| Variable | Purpose |
| --- | --- |
| `open_webui_secret_key` | Open WebUI session secret |
| `open_webui_oauth_client_id` | OIDC client ID |
| `open_webui_oauth_client_secret` | OIDC client secret |

### `group_vars/openclaw/vault.yml`

The required `vault_openclaw_discord_bot_token`,
`vault_openclaw_discord_user_id`, `vault_openclaw_discord_application_id`,
and `vault_openclaw_google_places_api_key` values are documented in
[group_vars/openclaw/README.md](../group_vars/openclaw/README.md).

## Social and communication vaults

### `group_vars/social/vault.yml`

| Variable | Purpose |
| --- | --- |
| `mastodon_db_password` | PostgreSQL password |
| `mastodon_secret_key_base` | Rails secret key base |
| `mastodon_otp_secret` | Two-factor authentication secret |
| `mastodon_vapid_private_key` | Push-notification private key |
| `mastodon_vapid_public_key` | Push-notification public key |
| `mastodon_aws_access_key_id` | S3 access key |
| `mastodon_aws_secret_access_key` | S3 secret key |
| `mastodon_active_record_encryption_deterministic_key` | Active Record deterministic key |
| `mastodon_active_record_encryption_key_derivation_salt` | Active Record derivation salt |
| `mastodon_active_record_encryption_primary_key` | Active Record primary key |

### `group_vars/matrix/vault.yml`

| Area | Variables |
| --- | --- |
| Synapse | `synapse_db_password`, `synapse_registration_shared_secret` |
| LiveKit | `livekit_api_key`, `livekit_api_secret` |
| S3 media | `synapse_s3_access_key_id`, `synapse_s3_secret_access_key` |
| MAS | `mas_db_password`, `mas_synapse_shared_secret`, `mas_encryption_key`, `mas_oidc_client_id`, `mas_oidc_client_secret` |

See the [Matrix role](../roles/matrix/README.md) for generation constraints and
OIDC setup.

## AI and backup vaults

| File | Variables |
| --- | --- |
| `group_vars/ai/vault.yml` | `searxng_secret_key`; see the [AI role](../roles/ai/README.md) |
| `group_vars/backup/vault.yml` | `borg_passphrase`, optional `borg_healthchecks_url`; see the [backup role](../roles/backup/README.md) |

## Finding drift

When a role gains a secret, update this index or its linked role README in the
same change. Search both `vault_` references and direct variables marked
`defined in vault`:

```sh
rg 'vault_|defined in vault|Vault secrets' roles group_vars
```
