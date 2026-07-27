# frp

This role deploys the frp server (`frps`) for authenticated tunnels. TCP
clients connect to port `7000`. Traefik exposes the authenticated dashboard at
`frp.tun.atelier.house` and routes `*.tun.atelier.house` HTTP tunnels to
frps's internal vhost port.

## Vault

Create `group_vars/frp/vault.yml` with:

```yaml
vault_frp_token: <shared-client-server-token>
vault_frp_dashboard_password: <dashboard-password>
```

Generate independent random values and distribute only `vault_frp_token` to
authorized frp clients. The dashboard username defaults to `admin`.

## DNS

The wildcard `*.tun.atelier.house` record and certificate route are owned by
the infrastructure gateway. Deploy the gateway after changing the tunnel
domain, then deploy frp:

```sh
make deploy-infra-gateway
make deploy-frp
```
