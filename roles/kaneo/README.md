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
- GitLab CI has published the full SHA configured as `kaneo_image_tag` to
  `registry.atelier.house/jedmund/kaneo`.

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
```

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

Run the gateway first so ddclient publishes the Kaneo hostname, then deploy the
application and refresh Borgmatic's PostgreSQL dump configuration:

```bash
make deploy-infra-gateway
make deploy-kaneo
make deploy-backup
```

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

Before changing `kaneo_image_tag`, run `make deploy-backup` and verify the
latest PostgreSQL dump. Deploy a new SHA to a disposable GitLab repository
first, then attach production repositories after issue, note, branch, merge
request, and duplicate-webhook smoke tests pass.

To roll back to an older fork image, restore the previous full SHA and run
`make deploy-kaneo`. Before running an upstream image, disable all SCM
integrations in Kaneo; upstream releases do not understand multi-repository or
GitLab external links. The additive database migration is intentionally left
in place during an image rollback.

Object storage is not configured in this stack. Kaneo attachment uploads need a
future S3-compatible storage addition.
