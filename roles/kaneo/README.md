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
- GitLab CI has published `registry.atelier.house/jedmund/kaneo:latest`,
  which it does on every default-branch build.

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

The deployment tracks `latest`, so `make deploy-kaneo` picks up whatever the
default branch last built. Kaneo applies its Drizzle migrations at API
startup, so a deploy can carry schema changes: run `make deploy-backup` and
verify the PostgreSQL dump first. Exercise a new build against a disposable
GitLab repository, then attach production repositories once issue, note,
branch, merge request, and duplicate-webhook smoke tests pass.

CI publishes an immutable full-SHA tag alongside `latest`. To roll back, or
to hold on a known-good build, set `kaneo_image_tag` to that SHA and run
`make deploy-kaneo`. Before running an upstream image, disable all SCM
integrations in Kaneo; upstream releases do not understand multi-repository or
GitLab external links. The additive database migration is intentionally left
in place during an image rollback.

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
