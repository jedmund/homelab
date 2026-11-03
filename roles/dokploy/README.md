# Dokploy

Dokploy runs in the `dokploy-vm` guest at `192.168.1.8`, hosted by libvirt on
`nuc-mini`. The `dokploy_host` role provisions the guest and its nightly VM dumps;
this role bootstraps Dokploy inside it. Both playbooks are explicit workflows,
excluded from `deploy/all.yml`.

## Source and images

The fork is maintained at [jedmund/dokploy on GitLab](https://git.atelier.house/jedmund/dokploy),
on `main`, following upstream `Dokploy/dokploy:canary`. Its
[fork runbook](https://git.atelier.house/jedmund/dokploy/-/blob/main/FORK.md)
describes validation, image publishing, and reviewed upstream-sync requests.

`dokploy_image` defaults to `registry.atelier.house/jedmund/dokploy:canary`.
GitLab CI publishes that moving tag and a full commit tag after validation.
Use the full commit tag to pin a release or select an older image. Image rollback
does not reverse database migrations; retain a pre-upgrade VM backup.
The public project registry supports anonymous pulls.

The fork enables self-hosted OIDC/SAML with `dokploy_enable_sso: true`.
`dokploy_sso_primary: true` opens SSO first while retaining password fallback.
Configure the PocketID provider in Dokploy's SSO settings after bootstrap.
The provider ID defaults to `pocketid` and its display name to `PocketID`, using
`dokploy_sso_provider_id` and `dokploy_sso_provider_name`. The fork uses these
public values to show a direct **Sign in with PocketID** button. The ID must
match the configured SSO provider; clear it to use email-based selection.

## Deployment

Use [Operations](../../docs/operations.md) for control-machine setup and
[Secrets](../../docs/secrets.md) for local vault placement. The role consumes
`dokploy_cloudflare_token` and `dokploy_acme_email` from `group_vars/dokploy/vault.yml`.
Do not replace existing values when working from a checkout without vaults.

Before deploying, verify the selected image exists, review upstream upgrade
requirements, and confirm a recoverable VM backup. Verify the guest is running
and SSH is reachable. Provision a new guest separately with
`make deploy-dokploy-host`; it can change host networking.

The host role allows this guest's outbound traffic and inbound TCP 22/80/443
and UDP 443 through UFW on `br0`. These forwarding rules are required when
bridge netfilter is enabled; host-to-guest access alone does not verify LAN
reachability. The gateway passes TLS for `deploy.atelier.house` and application
hostnames under `apps.atelier.house` to the guest.

The guest role routes `atelier.house` DNS queries to the homelab resolver at
`192.168.1.1` through a systemd-resolved drop-in. Public resolvers do not resolve
the private registry record. New guests also receive the homelab resolver in
their cloud-init network configuration.

From the repository root, when deployment is authorized:

```sh
make deploy-dokploy
```

The bootstrap installer initially installs upstream Dokploy. The role then
selects the fork image and configures its Traefik instance for Cloudflare DNS-01.
A repeat run can resolve a newer digest for the moving `canary` tag.

After deployment, inspect `docker service ls` and `docker ps` inside the guest.
Verify [deploy.atelier.house](https://deploy.atelier.house), PocketID login,
and a deployed application's route. Registry publishing alone does not establish
VM or application health.
