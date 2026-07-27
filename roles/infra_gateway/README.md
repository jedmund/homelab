# Infrastructure gateway

The gateway stack on `nuc-mini` owns Traefik, PocketID, TinyAuth, ddclient,
OpenSpeedTest, and Line. It also renders file-provider routes for services
Traefik cannot discover through Docker.

Vault inputs are indexed in [docs/vault.md](../../docs/vault.md).

## Line build-on-host exception

[Line](https://github.com/jedmund/line) is an in-house application that is
still built on the server. The role clones `line_repo` at `line_version` into:

```text
/opt/docker/infra-gateway/source/line
```

Every deployment refreshes the checkout. Compose rebuilds when the source
moves and builds the image if it is missing. This is a documented exception
to the normal in-house policy of pulling a CI-built image.

## Line authentication

Register an OIDC client in PocketID with redirect URI:

```text
https://atelier.house/auth/callback
```

Then set `line_oidc_client_id` and `line_oidc_client_secret` in
`group_vars/infra_gateway/vault.yml`. The same vault owns
`vault_line_admin_emails` and the optional Line integration keys listed in
the repository [vault index](../../docs/vault.md).

## DNS bootstrap

ddclient can update existing Cloudflare records but cannot create them. The
role delegates a Cloudflare DNS task to the controller to create any missing
records from `ddclient_atelier_subdomains`; subsequent ddclient runs maintain
their values.

Adding a public hostname therefore requires both its Traefik route and an
entry in `ddclient_atelier_subdomains`.
