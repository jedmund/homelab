# Inbox Zero deployment

This role deploys [Inbox Zero](https://github.com/elie222/inbox-zero) on
`nuc-mini`: the Next.js web app, PostgreSQL 16, Redis 7 with an HTTP Redis
proxy, the BullMQ worker, and a cron sidecar. The app is exposed at
`https://mail.atelier.house` through Traefik, signs in through Pocket ID OIDC
(Better Auth SSO plugin), manages Gmail mailboxes via Google OAuth and
Pub/Sub, and runs its models through the Open WebUI API. All credentials are
loaded from Ansible Vault.

## What runs

| Container | Purpose |
| --- | --- |
| `inboxzero_web` | Next.js app on `proxy-network` (Traefik labels) and `backend-internal` |
| `inboxzero_db` | PostgreSQL 16, `inboxzero` database; Borgmatic dumps it nightly |
| `inboxzero_redis` | Ephemeral Redis for cache and the BullMQ queue |
| `inboxzero_redis_http` | serverless-redis-http (Upstash REST protocol) for cache/rate limits |
| `inboxzero_worker` | BullMQ worker for durable background jobs |
| `inboxzero_cron` | curl loop pinging the scheduled-task endpoints (same intervals as upstream's `cron` service) |

The image is pinned to an upstream release tag (`2.30.0` at the time of
writing) with pull policy `missing`. Bump `inboxzero_image_tag` deliberately;
upstream publishes releases as `ghcr.io/elie222/inbox-zero:<version>` and
migration notes matter (see Upgrades).

## Authentication model

Read this before changing login settings; Inbox Zero's model is unusual.

- **Mailbox connection is the Google OAuth grant.** Signing in with Google
  creates the auth user *and* connects the Gmail mailbox (the OAuth client
  carries Gmail API scopes). Additional mailboxes are added in-app
  ("Add account") under the same user — `hello@jedmund.com` attaches to
  `justin@jedmund.com`'s login without a second account.
- **Pocket ID SSO is the login method.** The Better Auth SSO plugin also
  supports OIDC, but the admin UI only registers SAML providers, so this role
  seeds the organization and OIDC provider rows directly (guarded, idempotent
  SQL — `templates/oidc-seed.sql.j2`). Users sign in at
  `/login/sso` with their email and the organization slug `atelier`.
  The PocketID callback is
  `https://mail.atelier.house/api/auth/sso/callback/pocketid`.
- **The sign-up allowlist gates who becomes a user** for every method
  (SSO, Google). `AUTH_ALLOWED_EMAILS` is
  `justin@jedmund.com,hello@jedmund.com`; `ADMINS` is `justin@jedmund.com`.
  Every admin email must also appear in the allowlist (asserted).
- Email-OTP sign-in stays off: it requires Resend delivery and only works for
  users who opt in after signing in.

## Vault

Create `group_vars/inboxzero/vault.yml` (see [Secrets](../../docs/secrets.md)
for the table form). Generated values: `openssl rand -hex 32`, salt `-hex 16`.

```yaml
---
vault_inboxzero_postgres_password: "<openssl rand -hex 32>"
vault_inboxzero_redis_password: "<openssl rand -hex 32>"
vault_inboxzero_redis_http_token: "<openssl rand -hex 32>"
vault_inboxzero_auth_secret: "<openssl rand -hex 32>"
vault_inboxzero_email_encrypt_secret: "<openssl rand -hex 32>"
vault_inboxzero_email_encrypt_salt: "<openssl rand -hex 16>"
vault_inboxzero_internal_api_key: "<openssl rand -hex 32>"
vault_inboxzero_api_key_salt: "<openssl rand -hex 32>"
vault_inboxzero_cron_secret: "<openssl rand -hex 32>"

vault_inboxzero_google_client_id: "<Google Cloud OAuth client ID>"
vault_inboxzero_google_client_secret: "<Google Cloud OAuth client secret>"
vault_inboxzero_google_pubsub_topic_name: "projects/<project>/topics/inboxzero"
vault_inboxzero_google_pubsub_verification_token: "<openssl rand -hex 32>"

vault_inboxzero_openwebui_api_key: "<Open WebUI API key>"
vault_inboxzero_resend_api_key: "<Resend API key>"

vault_inboxzero_oidc_client_id: "<PocketID client ID>"
vault_inboxzero_oidc_client_secret: "<PocketID client secret>"
```

`AUTH_SECRET`, `EMAIL_ENCRYPT_SECRET`, and `EMAIL_ENCRYPT_SALT` protect
existing OAuth tokens and sessions; preserve them across redeploys.

## External setup

Complete these before the first deploy. The app tolerates missing values at
runtime, but the role's assertions require them.

### Google Cloud (Gmail + Pub/Sub)

1. Create a Google Cloud project and enable **Gmail API** and **Pub/Sub**.
2. Create an OAuth client (Web application) with redirect URI
   `https://mail.atelier.house/api/auth/callback/google` and store the client
   ID/secret in the Vault.
3. Create the Pub/Sub topic (`projects/<project>/topics/inboxzero`) and a push
   subscription to `https://mail.atelier.house/api/google/webhook` with the
   verification token from the Vault; grant publish on the topic to
   `gmail-api-push@system.gserviceaccount.com`.
4. Configure the OAuth consent screen for the Google accounts that will be
   connected; the test-user list must include `justin@jedmund.com` and
   `hello@jedmund.com` while the app is unverified.

`npx @inbox-zero/cli setup-google --project-id <project> --domain
mail.atelier.house` automates steps 3–4's API side from a machine with
`gcloud`; manual setup works too.

### PocketID

Create a client named `Inbox Zero` with callback
`https://mail.atelier.house/api/auth/sso/callback/pocketid`. Store the client
ID/secret in the Vault. The role seeds the organization (`Atelier`, slug
`atelier`) and the OIDC provider from these values on every deploy; the
discovery endpoint, scopes (`openid email profile`), and PKCE are fixed in
role defaults. Better Auth rejects OIDC discovery URLs outside its trusted
origins, so the env template sets `ADDITIONAL_TRUSTED_ORIGINS` to the Pocket
ID issuer when SSO is enabled.

### Open WebUI (models)

Create an API key in Open WebUI (`https://ai.atelier.house`, Settings >
Account) and store it as `vault_inboxzero_openwebui_api_key`. Both stacks
share `proxy-network`, so the app calls `http://open_webui:8080/openai/v1`
directly. Model ids are the llama-swap aliases Open WebUI exposes; verify the
exact ids the key can see before first use:

```bash
curl -s -H "Authorization: Bearer <key>" \
  https://ai.atelier.house/openai/v1/models | jq -r '.data[].id'
```

Defaults: `qwen3.8:27b` as the default model (economy, chat, and drafting
fall back to it) and `qwen3:4b` for nano classification. Account-level model
settings are locked (`NEXT_PUBLIC_AI_MODEL_SETTINGS_DISABLED=true`); change
the models in role defaults, not in the app. The 2.30.0 release configures
models with the legacy `DEFAULT_LLM_PROVIDER`/`DEFAULT_LLM_MODEL` style and
an optional `NANO_LLM_PROVIDER`/`NANO_LLM_MODEL` override; the newer
`DEFAULT_LLMS` chain format (with per-role fallback lists) arrives in later
releases — migrate the env template when bumping the tag. To route through
vLLM instead, point `inboxzero_llm_base_url` at `http://<max>:11438/v1`
(GLM profile) and adjust the model ids — one provider serves the whole
deployment, so vLLM and llama-swap cannot be mixed.

### Resend (transactional email)

Verify `jedmund.com` in Resend, create an API key, and store it as
`vault_inboxzero_resend_api_key`. Digests, follow-up reminders, meeting
briefs, and sign-in codes deliver through Resend; while the key is absent the
role asserts a failure if those feature flags are enabled, and the env
template omits them. Sender default: `Inbox Zero <noreply@jedmund.com>`.

## First deployment

Publish DNS, then deploy the gateway dependencies and the stack:

```bash
ansible-playbook -i inventory/hosts.yml deploy/ddclient.yml
make deploy-traefik
make deploy-inboxzero
make deploy-backup
```

`make deploy-inboxzero` waits for PostgreSQL, applies the OIDC seed, and
waits for the web health endpoint before returning. PocketID and Traefik must
already be deployed (they are part of the routine full deploy ahead of the
product stacks).

For a dry run:

```bash
ansible-playbook -i inventory/hosts.yml deploy/inboxzero.yml --check --diff \
  --vault-password-file ~/.ansible-vault-pass
```

## Sign in and connect mailboxes

1. Open `https://mail.atelier.house/login/sso`, enter `justin@jedmund.com`
   and organization slug `atelier`, and approve the PocketID prompt.
2. The first sign-in creates the user; the allowlist admits it. The account
   is an app admin via `ADMINS` (the `/admin` page works from this session).
3. Connect Gmail: either sign in with Google from the login page, or use the
   in-app add-account flow. Connect both `justin@jedmund.com` and
   `hello@jedmund.com` to the same user.
4. Verify Pub/Sub push: send a test message to the connected mailbox and
   confirm the assistant reacts without waiting for a cron cycle. Watch
   renewal runs every 6 hours regardless.

## Verify

On `nuc-mini`:

```bash
docker compose -f /opt/docker/inbox-zero/compose.yaml ps
docker exec inboxzero_db pg_isready -U inboxzero -d inboxzero
docker exec inboxzero_redis redis-cli ping
docker logs inboxzero_worker --tail 20
docker logs inboxzero_cron --tail 20
curl -fsS https://mail.atelier.house/api/health
docker exec inboxzero_db psql -U inboxzero -d inboxzero -tAc \
  "SELECT \"providerId\", \"domain\" FROM \"ssoProvider\""
```

The provider query should return `pocketid | jedmund.com`. Gatus monitors
`https://mail.atelier.house/` (group `apps`), and Borgmatic dumps
the `inboxzero` database after `make deploy-backup`.

## Upgrades

1. Read upstream release notes and migration notices for the target tag.
2. Bump `inboxzero_image_tag`, take a pre-upgrade backup
   (`docker exec inboxzero_db pg_dump -U inboxzero inboxzero > pre-upgrade.sql`
   on `nuc-mini`), then `make deploy-inboxzero`.
3. Confirm web health, worker logs, and one authenticated workflow (SSO sign
   in, a rule run, or a draft) before considering the upgrade done.

Rollback: revert `inboxzero_image_tag` to the previous release and redeploy.
Schema migrations applied by a newer image may not reverse cleanly; restore
the pre-upgrade dump if the application will not start (stop the stack first:
`docker compose -f /opt/docker/inbox-zero/compose.yaml down`).

## Notes and limitations

- **Redis is ephemeral.** Queue jobs and caches are lost on restart; Postgres
  is the source of truth and the cron container re-triggers periodic work.
- **The web healthcheck is shallow** (HTTP 200 on `/`, the login page).
  `/api/health` (with the deep database check behind `HEALTH_API_KEY`) arrives
  in a later release; switch the healthcheck, the role's web wait, and the
  Gatus endpoint when bumping the tag.
- **OIDC seeding owns the provider row.** Do not register a second SSO
  provider from `/admin` for the same organization; a manual SAML provider
  would survive, but edits to the seeded OIDC provider are overwritten by the
  next deploy on purpose (Vault is the source of truth).
- **The env template matches the pinned release.** 2.30.0 validates its
  environment strictly and rejects unknown-style values: it requires
  `DEFAULT_LLM_PROVIDER`, reads Redis HTTP settings under the legacy
  `UPSTASH_REDIS_*` names, and has no `MCP_SERVER_ENABLED` or
  delete/integration rule-action flags. The external API (API keys) works;
  the OAuth MCP server arrives in a later release — re-diff the env template
  against the new tag's `apps/web/.env.example` whenever bumping the image.
- Slack, Teams, and Telegram channels are the only supported chat surfaces;
  Discord is not supported, so they are left unconfigured.
- Composio-based integrations need a `COMPOSIO_API_KEY`; add it to the Vault
  and the env template before enabling those integrations.
- **Updates are deploy-driven.** An immutable release tag never changes
  under you, so Komodo's weekly digest report will not announce new upstream
  releases — watch upstream (GitHub releases) and apply through the upgrade
  procedure above. To adopt patch releases without editing defaults, pin the
  minor alias instead (for example `2.30`) and set
  `inboxzero_pull_policy: always`; every deploy then pulls the newest 2.30.x.
  Auto-update stays off because the web container runs database migrations at
  startup.
