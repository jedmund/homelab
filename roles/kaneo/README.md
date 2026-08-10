# Kaneo deployment

This role deploys Kaneo, PostgreSQL, and Redis on `nuc-mini`, exposes the app
at `https://kaneo.atelier.house`, uses PocketID for OIDC, and sends mail through
the shared SendGrid account. Repository synchronization uses a GitHub App. All
credentials and account-specific values are loaded from Ansible Vault files.

Kaneo does not currently provide an upstream GitLab integration. Its Gitea
adapter is not compatible with GitLab's API and webhook payloads, so the
self-hosted GitLab instance is intentionally not configured here.

## Prerequisites

- The repository's normal Ansible setup is complete (`make setup`).
- The `proxy-network` and `backend-internal` Docker networks exist; a normal
  prerequisites deployment creates them.
- `sendgrid_api_key` exists in `group_vars/compute_servers/vault.yml`; Kaneo
  reuses the same key as Mastodon and Dawarich.
- A PocketID OIDC client and a GitHub App have been created as described below.

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

vault_kaneo_oidc_client_id: "<PocketID client ID>"
vault_kaneo_oidc_client_secret: "<PocketID client secret>"

vault_kaneo_github_app_id: "<numeric GitHub App ID>"
vault_kaneo_github_app_name: "<GitHub App slug>"
vault_kaneo_github_webhook_secret: "<openssl rand -hex 32>"
vault_kaneo_github_private_key_base64: "<single-line base64 PEM>"
```

Generate the locally managed secrets independently:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
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
which the GitHub App is installed. Borgmatic includes `kaneo_postgres` in its
native PostgreSQL dumps after `make deploy-backup`.

Object storage is not configured in this stack. Kaneo attachment uploads need a
future S3-compatible storage addition.
