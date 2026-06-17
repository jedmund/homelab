# Hermes

Native macOS install on `mac-mini`, running the Hermes Agent Web Dashboard
as a user LaunchAgent. This deliberately installs the CLI/server path only;
Hermes Desktop is not part of this role.

## What the role does

- Installs Hermes Agent with the upstream non-Desktop installer under
  `~/.hermes/hermes-agent` and links `~/.local/bin/hermes`.
- Keeps browser support enabled by default so Hermes web/browser tools can
  work after model/tool setup.
- Runs `hermes dashboard --host 0.0.0.0 --port 9119 --no-open` through a
  user LaunchAgent.
- Preserves the rest of `~/.hermes/.env` and only manages an Ansible block
  for dashboard auth and public URL. The dashboard can still manage API
  keys in the same file.
- Exposes the dashboard through Traefik at `https://hermes.atelier.house`.

## Vault

Create `group_vars/hermes/vault.yml` before deploying:

```bash
ansible-vault create group_vars/hermes/vault.yml
```

Required:

- `vault_hermes_dashboard_basic_auth_secret` - stable 32+ byte signing
  secret, for example `openssl rand -base64 32`.
- Either `vault_hermes_dashboard_basic_auth_password_hash` (preferred) or
  `vault_hermes_dashboard_basic_auth_password`.

Optional:

- `vault_hermes_dashboard_basic_auth_username` - defaults to `admin`.

The upstream dashboard docs prefer a password hash so plaintext does not sit
at rest. After Hermes is installed, generate one with:

```bash
~/.hermes/hermes-agent/venv/bin/python - <<'PY'
from getpass import getpass
from plugins.dashboard_auth.basic import hash_password
print(hash_password(getpass("Hermes dashboard password: ")))
PY
```

For first bootstrap, using `vault_hermes_dashboard_basic_auth_password` in
the encrypted vault is acceptable; swap to the hash after the first deploy
if you want no plaintext in the rendered `.env`.

## Bring-up

1. Add the vault entries.
2. Deploy Hermes: `make deploy-hermes`.
3. Deploy the Traefik route: `make deploy-infra-gateway`.
4. Open `https://hermes.atelier.house` and sign in.
5. Run `hermes setup --portal` on `mac-mini` or use the dashboard to add
   model/tool API keys.

Verify the dashboard auth gate over the LAN, bypassing the outer TinyAuth
route:

```bash
curl -s http://192.168.1.7:9119/api/status | jq '.auth_required, .auth_providers'
```

Expected values are `true` and a provider list containing `basic`.
