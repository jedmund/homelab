# Degoog

Degoog runs as an independent search experiment on `max` at
`/opt/docker/degoog`. The public URL is `https://search.atelier.house`.

The route is protected by TinyAuth, whose only configured identity provider is
PocketID. The Degoog application uses an allow-all OAuth rule, so every
PocketID account can access it after login; the existing Atelier email
allowlist is not used for this route.

Degoog's host port is reachable only from `nuc-mini`, where Traefik runs. Do
not add a general LAN firewall rule for port 4444. The public route is the
authenticated access path.

## First deployment

Add the settings password to the Degoog vault at
`group_vars/degoog/vault.yml`:

```yaml
vault_degoog_settings_password: "<strong password>"
```

Deploy the stack and gateway configuration:

```sh
make deploy-prerequisites
make deploy-degoog
make deploy-infra-gateway
```

The normal `make deploy-all` workflow includes Degoog before the gateway route
is reconciled. After deployment, visit `https://search.atelier.house`, sign in
through PocketID, and install the desired engines from Degoog's Store. A fresh
instance has no engines until this step is completed.

For later API compatibility experiments, enable Degoog's “Serve the SearXNG
API shape” setting. The compatible endpoint is `/api/search`; existing
Open WebUI, n8n, Vane, and Kizuna integrations remain on the separate SearXNG
instance at `max:8889`.

## Verification

On `max`, verify the stack and readiness endpoint:

```sh
cd /opt/docker/degoog
docker compose ps
docker compose exec -T degoog curl -fsS http://127.0.0.1:4444/readyz
```

From a normal LAN client, `max:4444` should not be reachable. Through the
public hostname, anonymous requests should redirect to TinyAuth and an
authenticated PocketID user should reach Degoog.

## Rollback

Restore the SearXNG route and its TinyAuth application label, then deploy
Traefik and TinyAuth. Leave the Degoog stack in place for further experiments;
its data is independent of the SearXNG stack.

The existing backup role runs on `nuc-mini` and does not currently cover
`max:/opt/docker/degoog`. Treat this installation as rebuildable experiment
state until backup coverage is added.
