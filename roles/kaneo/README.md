# Kaneo deployment

This role deploys Kaneo, PostgreSQL, and Redis on `nuc-mini`, exposes the app
at `https://kaneo.atelier.house`, uses PocketID for OIDC, and sends mail through
the shared SendGrid account. Repository synchronization uses a GitHub App and
the private fork's GitLab integration. All credentials and account-specific
values are loaded from Ansible Vault files.

## Prerequisites

- The repository's normal Ansible setup is complete (`make setup`).
- The `proxy-network` and `backend-internal` Docker networks exist; a normal
  prerequisites deployment creates them.
- `sendgrid_api_key` exists in `group_vars/compute_servers/vault.yml`; Kaneo
  reuses the same key as Mastodon and Dawarich.
- A PocketID OIDC client, GitHub App, and GitLab OAuth application have been
  created as described below.
- The pinned image is available on the host. The 2.24.0 upgrade uses a verified
  local image archive; see Rollout and rollback. GitLab CI still publishes
  `latest` on default-branch builds, but this deployment does not follow it.

## Create the Vault

The ignored Vault file is loaded automatically because `nuc-mini` belongs to
the `kaneo` inventory group:

```bash
mkdir -p group_vars/kaneo
ansible-vault create group_vars/kaneo/vault.yml
```

Populate it with this complete schema:

```yaml
---
vault_kaneo_db_password: "<openssl rand -hex 32>"
vault_kaneo_redis_password: "<openssl rand -hex 32>"
vault_kaneo_auth_secret: "<openssl rand -hex 32>"
vault_kaneo_scm_secret_encryption_key: "<openssl rand -base64 32>"

vault_kaneo_registry_username: "<GitLab deploy-token username>"
vault_kaneo_registry_password: "<read_registry deploy token>"

vault_kaneo_oidc_client_id: "<PocketID client ID>"
vault_kaneo_oidc_client_secret: "<PocketID client secret>"

vault_kaneo_github_app_id: "<numeric GitHub App ID>"
vault_kaneo_github_app_name: "<GitHub App slug>"
vault_kaneo_github_webhook_secret: "<openssl rand -hex 32>"
vault_kaneo_github_private_key_base64: "<single-line base64 PEM>"

vault_kaneo_gitlab_oauth_client_id: "<GitLab application ID>"
vault_kaneo_gitlab_oauth_client_secret: "<GitLab application secret>"

vault_kaneo_garage_rpc_secret: "<openssl rand -hex 32>"
vault_kaneo_garage_admin_token: "<openssl rand -hex 32>"
vault_kaneo_garage_metrics_token: "<openssl rand -hex 32>"
vault_kaneo_garage_access_key_id: "<printed by garage_bootstrap.sh>"
vault_kaneo_garage_secret_access_key: "<printed by garage_bootstrap.sh>"
```

The three Garage tokens are generated locally and must be present before the
first deploy. The access key pair is left empty until `garage_bootstrap.sh`
creates it on the host; see Object storage below.

Generate the locally managed secrets independently:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -base64 32
```

The Redis password must remain hexadecimal because the entrypoint safely writes
it to Redis configuration without shell interpolation. Encode the GitHub App
private key as one line before placing it in the Vault:

```bash
openssl base64 -A -in kaneo-app.private-key.pem
```

Do not commit the Vault file or the GitHub private key. `**/vault.yml` is
ignored by Git, but verify with `git status` before committing other changes.

## PocketID OIDC

Create a PocketID OIDC client named `Kaneo` with this callback URL:

```text
https://kaneo.atelier.house/api/auth/oauth2/callback/custom
```

Copy the client ID and secret into the Vault. The role configures PocketID's
authorization, token, user-info, discovery, and logout endpoints, requests the
`openid profile email` scopes, and enables PKCE. Guest access, password
registration, and the local login form are disabled; successful PocketID users
are provisioned by Kaneo on first sign-in.

## SendGrid SMTP

Kaneo reuses `sendgrid_api_key` from `group_vars/compute_servers/vault.yml`.
No Kaneo-specific SMTP secret is required. The role connects to
`smtp.sendgrid.net:587` with STARTTLS, authenticates as `apikey`, and sends from
the same verified `noreply@atelier.house` address used by Dawarich.

## GitHub App

Create a GitHub App with:

- Homepage URL: `https://kaneo.atelier.house`
- Webhook URL: `https://kaneo.atelier.house/api/github-integration/webhook`
- Repository permissions: Issues read/write; Pull requests, Metadata, and
  Contents read
- Webhook events: Issues, Issue comments, Pull requests, and Push

Copy the App ID and slug into the Vault, generate a private key, encode it as
described above, and install the App on each repository Kaneo should access.
After deployment, connect repositories from each Kaneo project's integration
settings. These credentials enable repository synchronization, not GitHub
sign-in; PocketID remains the only login provider.

## GitLab integration

Create a confidential GitLab OAuth application for the `api` scope with this
redirect URI:

```text
https://kaneo.atelier.house/api/gitlab-integration/oauth/callback
```

Store the application ID and secret in the Kaneo Vault. Create a separate
project or group deploy token with only `read_registry`, then store its
username and token in the same Vault. The deploy token is used only by Docker
on `nuc-mini`; Kaneo workspace connections use OAuth or encrypted group access
tokens entered through the application.

Kaneo advertises `https://git.atelier.house` to browsers and webhooks but calls
GitLab at `http://gitlab` over `backend-internal`. This exact mapping is set by
the role and avoids enabling private destinations for user-controlled SCM
URLs.

## First deployment

Publish DNS first so ddclient registers both `kaneo.atelier.house` and
`files.kaneo.atelier.house`, then deploy the application and refresh
Borgmatic's volume and PostgreSQL dump configuration:

```bash
ansible-playbook -i inventory/hosts.yml deploy/ddclient.yml
make deploy-traefik
make deploy-kaneo
make deploy-backup
```

Traefik is redeployed because `files.kaneo.atelier.house` is a three-level
name: the `*.atelier.house` wildcard certificate does not cover it, so
`roles/traefik` carries an explicit `*.kaneo.atelier.house` entry alongside the
existing `*.sort` and `*.tun` ones.

That first `make deploy-kaneo` brings the stack up with an empty Garage: no
cluster layout, no bucket, no access key. Kaneo boots and everything except
uploads works. Finish storage with the bootstrap in Object storage below, then
run `make deploy-kaneo` a second time so `kaneo.env` picks up the `S3_*`
credentials.

For a dry run of Kaneo itself:

```bash
ansible-playbook -i inventory/hosts.yml deploy/kaneo.yml --check --diff --ask-vault-pass
```

If `~/.ansible-vault-pass` exists, use `--vault-password-file
~/.ansible-vault-pass` instead of `--ask-vault-pass`.

## Verify

On `nuc-mini`, check the stack and its dependencies:

```bash
docker compose -f /opt/docker/kaneo/compose.yaml ps
docker exec kaneo_postgres pg_isready -U kaneo -d kaneo
docker exec kaneo_redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping'
curl -fsS https://kaneo.atelier.house/api/health
```

Then sign in through PocketID, send a test email, and connect a repository on
which the GitHub App is installed. Also authorize the GitLab workspace
connection, attach a disposable repository, and confirm that Kaneo provisions
its signed project webhook. Borgmatic includes `kaneo_postgres` in its native
PostgreSQL dumps after `make deploy-backup`.

## Rollout and rollback

The deployment is pinned to `workflow-40a1e34ac728`, built from the
reviewed Kaneo Git tree `40a1e34ac728c414d8fcac393f2802007084caf2`.
No commit or mutable registry tag was published for this deployment. The image
archive is retained at
`/opt/docker/kaneo/upgrade/workflow-40a1e34ac728/image.tar` on `nuc-mini`.
The role's `kaneo_pull_policy: missing` preserves that local image on ordinary
`make deploy-kaneo` runs. For a replacement host, securely transfer the archive
and run the upgrade playbook's staging phase before deploying the role.

`deploy/kaneo-upgrade.yml` stages an AMD64 image and runs the candidate's
read-only migration preflight before permitting downtime. Create a local JSON
variables file containing:

```json
{
  "kaneo_upgrade_id": "workflow-40a1e34ac728",
  "kaneo_upgrade_image": "registry.atelier.house/jedmund/kaneo:workflow-40a1e34ac728",
  "kaneo_upgrade_image_id": "sha256:1d4674fc58aee8c4b76fb620ca293469fa803dfc6026287f1de109bfb0c32e4a",
  "kaneo_upgrade_archive": "/absolute/path/to/image.tar",
  "kaneo_upgrade_source": "/absolute/path/to/reviewed/kaneo/source"
}
```

The image ID above is the OCI manifest digest reported by Docker 29 on the
NUC. It matches `index.json` in the saved archive. Older Docker image stores
report the configuration digest instead; inspect and verify the archive,
configuration, and layers before supplying a different expected ID.

```bash
# Staging and read-only preflight; production continues running.
ansible-playbook deploy/kaneo-upgrade.yml --limit nuc-mini -e @/path/to/upgrade.json
# Explicit maintenance window: stop Kaneo, back up, deploy, verify.
ansible-playbook deploy/kaneo-upgrade.yml --limit nuc-mini -e @/path/to/upgrade.json \
  -e kaneo_upgrade_apply=true
```

The apply phase retains the previous image under a rollback tag, archives the
existing configuration, stops the app and its workers, takes a PostgreSQL
custom-format dump, verifies its archive index, and records checksums. It then
runs the standard Kaneo role, checks container/public health and exact image
identity, and repeats the migration preflight. Backups and `images.json` are in
`/opt/docker/backups/kaneo-<upgrade-id>-<timestamp>/`, protected with mode 0700.
These contain production secrets/data; do not copy them into the repository or
use them in development databases.

On a deployment/health failure, the playbook restores the saved configuration
and starts the recorded previous image against the additive schema. It never
automatically restores the database. For a later manual rollback, load the
recorded previous image, set `kaneo_image_tag` to its retained rollback tag and
`kaneo_image` to `kaneo-rollback`, then use `make deploy-kaneo`. Update the local
pin as well so the next deployment does not reinstall the candidate. Keep
`AUTH_SECRET`, `SCM_SECRET_ENCRYPTION_KEY`, and provider credentials unchanged.

If database restoration becomes necessary, stop application writes and workers,
verify `SHA256SUMS`, and restore the pre-upgrade dump to a clean production
database under a separate recovery procedure. This loses writes since the dump;
reconcile remote issue creation before restarting SCM workers. Do not run an
upstream-only image with the fork's SCM integrations enabled.

Production acceptance includes PocketID login, an existing task, uploads, and
GitLab/GitHub/Gitea sync on designated test repositories. Public health and an
OIDC redirect alone do not prove authenticated workflows or provider sync.

### Production deployment record — 2026-09-16

The maintenance playbook completed on `nuc-mini` with 44 successful tasks and
no failures or rollback. Running image manifest:
`sha256:a44185968ff6b452e60e4dc994b39cb047ca26e1a067647a4276a0054e2ed53e`.

Rollback artifacts:
`/opt/docker/backups/kaneo-2.24.0-d52ba238216d-20260916T020514/`.
Previous image:
`sha256:5b84c6c4654844cc85cdfb72379d6868c1b2ab2825e296900621a568d3fa0669`.
Retained tag: `kaneo-rollback:2.24.0-d52ba238216d-20260916T020514`.

Post-upgrade checks passed: both backup checksums, container and HTTPS health,
read-only migration preflight, 49 migration records and all three new tables,
Redis adapter and scheduler startup. Counts before/after matched: 47 tasks,
3 projects, 6 repositories, 1 SCM connection, 44 external links, and 0 sync
jobs. A browser reached PocketID from the production site without JavaScript
errors. Authenticated UI, uploads, and real-provider mutation flows were not
exercised during this deployment.

### GitLab workflow deployment — 2026-09-16

Deployed `workflow-40a1e34ac728` via `deploy/kaneo-upgrade.yml`: 44 successful
tasks, no failures or rollback. Source tree:
`40a1e34ac728c414d8fcac393f2802007084caf2`. Running manifest:
`sha256:1d4674fc58aee8c4b76fb620ca293469fa803dfc6026287f1de109bfb0c32e4a`.

Fresh backup and rollback metadata:
`/opt/docker/backups/kaneo-workflow-40a1e34ac728-20260916T024037/`.
Previous image manifest:
`sha256:a44185968ff6b452e60e4dc994b39cb047ca26e1a067647a4276a0054e2ed53e`.
Retained rollback tag: `kaneo-rollback:workflow-40a1e34ac728-20260916T024037`.

Verified backup checksums, unchanged record counts (47 tasks, 3 projects,
6 repositories, 1 SCM connection, 44 external links, 0 sync jobs), healthy
application, Redis adapter and scheduler, and the production PocketID redirect
without browser errors. Production HTTPS serves `workflow-DTYMcXk4.js` with
the GitLab event mappings and reset control. No new database migrations were
introduced; the migration journal remains at 49 entries. Existing production
workflow rules were not changed. Workflow controls and synthetic webhook events passed local tests;
authenticated interaction and real provider events were not exercised on production.

## Object storage

Attachment and pasted-image uploads in task descriptions and comments are
backed by a per-stack Garage instance (`kaneo-garage`), the same S3 pattern
`roles/kizuna` and `roles/gitlab` use. The bucket is private; Kaneo serves
uploaded files back through its own `/api/asset/:id`.

`S3_ENDPOINT` is the public Traefik route (`https://files.kaneo.atelier.house`),
not the internal `kaneo-garage:3900`. This is deliberate and differs from
Kizuna, which splits the two. Kaneo exposes a single endpoint variable, and the
browser PUTs directly to the presigned URL the API mints against it, so that
endpoint has to resolve from the browser. Only the S3 API port is routed; the
admin and k2v ports stay on the internal network. The hostname is registered in
`roles/ddclient` and its certificate comes from the `*.kaneo.atelier.house`
entry in `roles/traefik`.

Object blocks live on the Files NAS share under `Kaneo/Garage`
(`kaneo_garage_data_nas_enabled`); the SQLite metadata volume stays local so
Borg can capture it with a consistent snapshot, which is why
`roles/backup` lists `kaneo_kaneo-garage-meta` and not the data volume.

### Bootstrap

After the first `make deploy-kaneo`, on `nuc-mini`:

```bash
/opt/docker/kaneo/garage_bootstrap.sh
```

It assigns the single-node cluster layout, creates the `kaneo-uploads` bucket,
generates an access key, and prints it. Add both halves to the Vault as
`vault_kaneo_garage_access_key_id` / `vault_kaneo_garage_secret_access_key`,
then run `make deploy-kaneo` again. Every step is gated on current state, so
re-running the script is safe.

The deploy itself re-asserts the two declarative steps on every run: granting
the key read+write+owner on the bucket, and setting the bucket CORS rule that
permits the browser's cross-origin presigned PUT. Both skip cleanly while the
Vault access key is still empty.

### Verify uploads

```bash
docker exec kaneo-garage /garage status
docker exec kaneo-garage /garage bucket info kaneo-uploads
curl -sSI https://files.kaneo.atelier.house/kaneo-uploads/
```

The `curl` should return an S3 403 (the bucket is private), not a connection or
TLS error. Then open a task in the browser, paste an image into the description
and attach a PDF to a comment: images render inline, other files render as
attachment cards. Reload to confirm both are served back after a round trip.
