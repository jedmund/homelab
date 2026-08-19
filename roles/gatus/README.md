# Gatus deployment

This role deploys [Gatus](https://github.com/TwiN/gatus) on `nuc-mini` and
exposes it at `https://status.atelier.house`. It watches two different things:
whether services respond, and whether a few invariants that plain uptime
monitoring cannot see still hold. PocketID provides OIDC login and alerts go
out over the shared SendGrid account.

Every check is config-as-code in `defaults/main.yml`. Adding one is a defaults
edit and a redeploy, reviewed in a PR like any other change. That is the reason
this role exists rather than Uptime Kuma, whose monitors live in a SQLite
database with no full REST API and would sit outside Ansible entirely.

## What it checks

- **GitLab runner liveness.** Reads `/api/v4/runners/:id` for each runner and
  requires `online == true`. This is the check that would have caught runner 2
  sitting dead for 24 days in August 2026 while GitLab, the mac, and the runner
  process all looked healthy. A paused runner still reports online, so pausing
  one for maintenance does not alert.
- **Service reachability** for core infrastructure and the main apps. Expected
  status codes were probed against the live services rather than assumed; the
  401s are auth middleware answering correctly.
- **Wildcard certificate runway**, alerting 14 days before `*.atelier.house`
  expires, to catch a Cloudflare DNS challenge renewal that quietly stopped.

## Known gaps

Gatus runs on `nuc-mini` alongside most of what it watches, so it cannot report
on `nuc-mini` itself going down. Beszel already covers host and container
health from its own agents, and the borgmatic Healthchecks.io check is an
independent dead-man's switch. If you want coverage for the monitor itself,
give Gatus its own Healthchecks.io check.

Runner detection latency is roughly two hours. GitLab only rewrites
`contacted_at` every 40 to 55 minutes and treats a runner as online for two
hours after its last contact, so polling faster cannot tighten it. A
runner-side dead-man's switch would be the instrument for minute-level
detection. Two hours against the 24 days it previously took is the win here.

## DNS

`status.atelier.house` has no public record yet, so the dashboard resolves on
the LAN only. Add a Cloudflare A record if you want to reach it from outside.
Note that Gatus deliberately uses the container's default public resolver, so
the reachability checks exercise the real external path rather than a LAN
shortcut. `registry.atelier.house` is internal-only by design and is pinned to
Traefik with `extra_hosts` because a public resolver cannot find it.

## Prerequisites

- The repository's normal Ansible setup is complete (`make setup`).
- The `proxy-network` Docker network exists; a normal prerequisites deployment
  creates it.
- `sendgrid_api_key` exists in `group_vars/compute_servers/vault.yml`; Gatus
  reuses the same key as Kaneo and Dawarich.
- A PocketID OIDC client and a GitLab API token have been created as below.

## Create the PocketID client

Create a client in PocketID with this exact callback URL. Gatus requires the
redirect URL to end in `/authorization-code/callback`:

```
https://status.atelier.house/authorization-code/callback
```

## Create the GitLab token

The runner endpoints read instance-wide runner state, so the token must belong
to an administrator. Scope it to `read_api` only.

Note that the self-service endpoint (`POST /user/personal_access_tokens`) only
accepts the `k8s_proxy` and `self_rotate` scopes, so it cannot mint this token.
Use the admin endpoint against your own user id:

`glab api` sends a JSON body, so `scopes` has to be a JSON array. The form
encoding from GitLab's own curl examples (`scopes[]=read_api`) creates a field
literally named `scopes[]` and the request fails with `scopes is missing`.

```sh
# Your user id
glab api user | jq .id

glab api --method POST "users/<user-id>/personal_access_tokens" \
  -F name=gatus-runner-monitor \
  -F description="Gatus runner liveness checks" \
  -F 'scopes=["read_api"]'
```

The token is shown once, in the `token` field of the response. Creating it in
the UI under User Settings, Access Tokens works equally well.

Omitting `expires_at` only works while the instance allows non-expiring
tokens. That is an instance-wide setting, not a per-token one:

```sh
glab api application/settings | jq .require_personal_access_token_expiry
glab api --method PUT application/settings \
  -F require_personal_access_token_expiry=false
```

With it left at `true`, pass `-F expires_at=<YYYY-MM-DD>` and expect the runner
checks to start failing when the token lapses, which reads as a runner outage
rather than an expired credential.

## Create the Vault

The ignored Vault file is loaded automatically because `nuc-mini` belongs to
the `gatus` inventory group:

```bash
mkdir -p group_vars/gatus
ansible-vault create group_vars/gatus/vault.yml
```

Populate it with this complete schema:

```yaml
---
vault_gatus_oidc_client_id: "<PocketID client ID>"
vault_gatus_oidc_client_secret: "<PocketID client secret>"
vault_gatus_gitlab_token: "<GitLab admin token, read_api scope>"
vault_gatus_alert_to: "<address alerts are sent to>"
vault_gatus_discord_webhook_url: "<Discord channel webhook, optional>"
```

| Vault key | Purpose |
| --- | --- |
| `vault_gatus_oidc_client_id` | PocketID client ID for dashboard login |
| `vault_gatus_oidc_client_secret` | PocketID client secret |
| `vault_gatus_gitlab_token` | GitLab admin token, `read_api`, reads runner state |
| `vault_gatus_alert_to` | Email alert recipient; kept out of this public repo |
| `vault_gatus_discord_webhook_url` | Discord channel webhook; omit to disable Discord |

The OIDC block and each alerting provider are omitted from the rendered config
while their keys are empty, so a first deploy comes up unauthenticated and
silent rather than failing to start. Fill the vault before relying on it.

## Alerting to Discord

Email and Discord are independent: configure either, both, or neither. Every
endpoint alerts through whichever providers are present, so adding the webhook
fans all 16 existing checks out to Discord without touching them.

Create the webhook in Discord under Server Settings, Integrations, Webhooks.
It is scoped to one channel, so the channel is chosen there rather than in this
role. Treat the URL as a credential: anyone holding it can post to that
channel, which is why it lives in the vault and reaches the config as an
environment variable rather than being written into a readable file.

An embed on its own does not notify anyone. To make alerts actually ping, set
`gatus_discord_message_content` to a role or user mention, which is sent as
plain content ahead of the embed:

```yaml
gatus_discord_message_content: "<@&000000000000000000>"
```

## Deploy

```sh
ansible-playbook deploy/gatus.yml
```

## Notes

The container declares no healthcheck on purpose. The Gatus image is built
from scratch and ships only the `gatus` binary, with no shell, curl, or wget
to run a probe with, so a declared probe would fail on every run and leave the
container permanently unhealthy while it serves fine. Gatus exposes `/health`
over HTTP for anything checking from outside the container.

Config files under `config/` are mode `0644` and contain no secrets. They
carry `${VAR}` placeholders that Gatus substitutes from the environment at
load; the real values live in `env/gatus.env` at `0600`.
