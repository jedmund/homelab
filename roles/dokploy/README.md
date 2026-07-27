# Dokploy

The `dokploy_host` role provisions the libvirt VM. This role runs inside that
VM, installs Dokploy once, switches the Swarm service to the configured fork,
and reconciles Traefik DNS-01 certificate settings.

## Vault

Create `group_vars/dokploy/vault.yml` with:

```yaml
dokploy_cloudflare_token: <zone-dns-edit-token>
dokploy_acme_email: <letsencrypt-registration-email>
```

## Deployment and first setup

```sh
make deploy-dokploy-host
make deploy-dokploy
```

After the install:

1. Open `http://<dokploy-vm-ip>:3000` and create the first administrator.
2. Configure PocketID OIDC in Dokploy.
3. Under Web Server, set the server domain and choose Let's Encrypt. The role
   has already configured Cloudflare DNS-01.
4. Add Cloudflare A records for the Dokploy host and desired application
   wildcard.

The upstream installer is not idempotent, so the role runs it only when
`/etc/dokploy` does not exist. Later deployments reconcile the managed Swarm
image, environment, and Traefik configuration.
