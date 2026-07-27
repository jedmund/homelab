# Service catalog

This is the repository-wide role index. Service-specific bootstrap, migration,
and recovery instructions belong in the linked role README rather than the
root README.

Most product roles are deployed with `make deploy-<role>`, replacing
underscores with hyphens. Run `make help` for the exact target names.
Base roles are composed by `make deploy-prerequisites`.

In-house services are marked `[in-house]`. See
[CONVENTIONS.md](../CONVENTIONS.md) for their image and deployment policy.

## Base host capabilities

| Role | Responsibility |
| --- | --- |
| `prerequisites` | DNS fallback, passwordless sudo, and shell environment |
| `docker` | Docker Engine and runtime configuration |
| `networks` | Shared Docker networks |
| `docker-volumes` | NFS-backed Docker volumes |
| `firewall` | UFW policy and service rule groups |
| `security` | SSH hardening |
| [`monitoring`](../roles/monitoring/README.md) | Netdata parent/child monitoring |

These roles target `compute_servers` through `deploy/prerequisites.yml`.

## Infrastructure and access

| Role | Services or responsibility |
| --- | --- |
| [`infra_gateway`](../roles/infra_gateway/README.md) | Traefik, PocketID, TinyAuth, ddclient, OpenSpeedTest, and Line `[in-house]` |
| `infra_core` | Komodo Core, Periphery, and MongoDB on `nuc-mini` |
| [`infra_periphery`](../roles/infra_periphery/README.md) | Standalone Komodo Periphery agent on `max` |
| [`beszel`](../roles/beszel/README.md) | Beszel monitoring hub |
| `beszel_agent` | Beszel agents, deployed with `make deploy-beszel-agents` |
| `dokploy_host` | KVM/libvirt VM that hosts Dokploy |
| [`dokploy`](../roles/dokploy/README.md) | Dokploy bootstrap inside its VM |
| [`frp`](../roles/frp/README.md) | frp tunnel proxy and dashboard |

## Media

| Role | Services |
| --- | --- |
| `gluetun` | Gluetun VPN gateway |
| `prowlarr` | Prowlarr |
| `qbittorrent` | qBittorrent |
| `sonarr` | Sonarr |
| `radarr` | Radarr |
| `lidarr` | Lidarr |
| `seerr` | Seerr |
| `unpackerr` | Unpackerr |
| `jdownloader` | JDownloader |
| `pinchflat` | Pinchflat |
| `slskd` | slskd |
| `qui` | Qui |
| [`musicbrainz`](../roles/musicbrainz/README.md) | MusicBrainz mirror |
| `romm` | RomM and MariaDB |
| `plex` | Plex |
| `multi_scrobbler` | Multi-Scrobbler |
| `tunarr` | Tunarr |
| `stash` | Stash |

## Product and utility stacks

| Role | Services |
| --- | --- |
| `immich` | Immich, machine learning, Redis, and PostgreSQL |
| `papra` | Papra |
| `homebox` | Homebox |
| `album_sort` | Album Sort `[in-house]` and Beets |
| `dawarich` | Dawarich, Sidekiq, PostgreSQL, Redis, and Photon |
| `miniflux` | Miniflux, PostgreSQL, Reactflux, and FiveFilters |
| `karakeep` | Karakeep, Chrome, and Meilisearch |
| `kavita` | Kavita |
| `strudel` | Strudel `[in-house]` |
| `blinko` | Blinko and PostgreSQL |
| `obsidian_livesync` | CouchDB for Obsidian LiveSync |
| `n8n` | n8n and PostgreSQL |
| `changedetection` | ChangeDetection.io |
| `copyparty` | Copyparty |
| [`hugginghack`](../roles/hugginghack/README.md) | HuggingHack model browser and downloader |
| [`kibble`](../roles/kibble/README.md) | Kibble `[in-house]` and its Garage object store |
| [`kizuna`](../roles/kizuna/README.md) | Kizuna API, app, workers, PostgreSQL, Redis, and Garage `[in-house]` |
| [`vane`](../roles/vane/README.md) | Vane answer engine `[in-house]` |
| [`petlibro`](../roles/petlibro/README.md) | catbro and Mosquitto |

## Content and social

| Role | Services |
| --- | --- |
| `social` | Mastodon, PostgreSQL, Redis, and streaming |
| [`matrix`](../roles/matrix/README.md) | Synapse, Element, MAS, LiveKit, and PostgreSQL |

## Development and agents

| Role | Services or responsibility |
| --- | --- |
| [`gitlab`](../roles/gitlab/README.md) | GitLab, the `nuc-mini` Docker runner, Renovate, and CI cache |
| `development_linux` | GitLab Docker runner on `max` |
| `development_macos` | GitLab shell runner on `mac-mini` |
| `open_webui` | Open WebUI |
| `paseo_relay` | Paseo Relay |
| `paseo_daemon` | Native Paseo daemon on macOS |
| `agents_linux` | Pi, OpenCode, and Edra agent tooling on Linux |
| [`openclaw`](../roles/openclaw/README.md) | Native OpenClaw agent on macOS |

## AI and GPU

| Role | Services or responsibility |
| --- | --- |
| [`ai`](../roles/ai/README.md) | llama-swap, Whisper, Kokoro, TEI, SearXNG, and Playwright |
| `vllm` | DeepSeek V4 Flash serving path |
| [`sglang`](../roles/sglang/README.md) | Parked SGLang serving stack |
| `gpu_tools` | `hwsummary` and GPU burn-in helpers |

## Backup

| Role | Services |
| --- | --- |
| [`backup`](../roles/backup/README.md) | Borgmatic, Borg-UI, and scheduled snapshots |

See [Database backups](database-backups.md) for manual database-level
procedures. The backup role README is authoritative for the scheduled Borg
workflow.
