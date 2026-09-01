# Aurral

[Aurral](https://github.com/lklynet/aurral) is deployed on `nuc-mini` at
`https://aurral.atelier.house`. It is a Lidarr companion for music discovery,
flows, playlists, and downloads. The container uses Aurral's native OIDC
support with PocketID; TinyAuth is only an initial-setup guard around the
otherwise unauthenticated onboarding API.

The role pins `ghcr.io/lklynet/aurral:2.8.0`. Bump
`aurral_image_tag` deliberately when upgrading.

## PocketID and Vault

Create a confidential PocketID client named `Aurral` with this exact callback:

```text
https://aurral.atelier.house/sso/callback
```

Limit the PocketID client to the people who should be able to use Aurral. Then
create `group_vars/aurral/vault.yml` with the client credentials and the exact
PocketID `preferred_username` values that should become Aurral administrators:

```yaml
---
vault_aurral_oidc_client_id: "<client ID>"
vault_aurral_oidc_client_secret: "<client secret>"
vault_aurral_oidc_admin_users:
  - "<preferred_username>"
```

Keep the admin value as a YAML list, even for one user. Every other permitted
PocketID user is provisioned with Aurral's `user` role. Role changes from this
list take effect on the user's next OIDC login.

## First deployment

Deploy the DNS record and refreshed TinyAuth policy before opening Aurral. A
routine `make deploy-all` reconciles all three; for a targeted rollout use:

```bash
make -C deploy ddclient
make -C deploy tinyauth
make deploy-aurral
```

Before opening Aurral for the first time, sign in at
`https://auth.atelier.house` to establish the TinyAuth cookie. Then open
`https://aurral.atelier.house` and complete onboarding:

1. Create a strong, unique local administrator as a break-glass account. Leave
   local-network auto-login disabled.
2. Connect Lidarr at `http://lidarr:8686` with its API key and verify the
   connection. Aurral requires this connection to finish onboarding.
3. After onboarding completes, log out and use the OIDC login. Confirm a
   username listed in `vault_aurral_oidc_admin_users` receives the admin role.

The setup API remains behind TinyAuth after onboarding, but normal application
traffic uses Aurral's native PocketID OIDC directly.

## Storage and integrations

Aurral receives the same external Docker volumes and paths used by the existing
music services:

| Data | Aurral path | Access |
|------|-------------|--------|
| Lidarr music library | `/music` | Read-only |
| Shared ingest/downloads | `/downloads` | Read/write |
| Aurral database, users, settings, and jobs | `/config` | Read/write, local |

Use these values in Aurral:

- Downloads Folder: `/downloads/aurral`
- Lidarr URL: `http://lidarr:8686`
- slskd URL: `http://slskd:5030`

Lidarr and slskd already use `/music` and `/downloads`, so remote path mappings
are unnecessary. Aurral can play canonical Lidarr files through its built-in
player; do not configure a Navidrome playback integration.

After setup, run **Settings > Storage health > Run Checks** and **Settings >
Lidarr > Test library access**. Verify the service itself with:

```bash
curl -fsS https://aurral.atelier.house/api/health/live
```

The expected response is `{"status":"ok"}`.
