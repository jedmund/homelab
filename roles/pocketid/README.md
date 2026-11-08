# Pocket ID

Deploys the OIDC provider at `https://id.atelier.house` on `nuc-mini` and an
nginx sidecar for the Apple app-site-association endpoint. Deployment files
and persistent data remain under `/opt/docker/pocketid`.

## Updates

`pocketid_image` follows `ghcr.io/pocket-id/pocket-id:v2`, the floating tag in
the [upstream Compose example](https://github.com/pocket-id/pocket-id/blob/main/docker-compose.yml).
It advances with v2 releases. The nginx sidecar is pinned to an image digest
in `pocketid_aasa_image`. Komodo skips digest-pinned images during update
checks, avoiding Docker Hub lookups for this static responder. Updating nginx
requires an explicit change to that reference and deployment.

Komodo's manual update check and weekly digest report can detect changes to
the `v2` image after Ansible writes that reference into the host Compose file.
Polling and automatic deployment remain disabled. The normal Ansible
deployment uses the shared `always` pull policy and installs the current v2
image:

```sh
make -C deploy pocketid
```

Before deploying, review the [upstream upgrade notes](https://pocket-id.org/docs/setup/upgrading)
and confirm a recoverable backup of `config/pocketid/data`, the environment
file, and the existing encryption key. See the [backup runbook](../backup/README.md)
for configured coverage and restore limits. Record the running image's
repository digest before an upgrade.

After deployment, run on `nuc-mini`:

```sh
docker exec pocketid /app/pocket-id healthcheck
curl --fail --silent --show-error https://id.atelier.house/.well-known/openid-configuration
curl --fail --silent --show-error https://id.atelier.house/.well-known/apple-app-site-association
```

Verify passkey login and an application's OIDC login separately.

## Rollback

Set `pocketid_image` to the recorded pre-upgrade repository digest or release
tag in [defaults/main.yml](defaults/main.yml), then redeploy. Pocket ID rejects
an older version after a newer version migrates its database; restore the
matching pre-upgrade data before starting the previous image. Preserve the
existing encryption key; changing it invalidates stored OIDC client secrets.
