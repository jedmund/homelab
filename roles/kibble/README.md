# Kibble

Deploys the feeder control service on `nuc-mini` at
`https://cat.atelier.house`. Kibble provides the application UI, MQTT bridge,
video service, and in-process Kalay server. The
[Petlibro role](../petlibro/README.md) supplies the Mosquitto broker.

## Identity and storage

The role, container, image, and Komodo resource are named `kibble`. Existing
storage retains the `feederhub` name:

| Item | Value |
| --- | --- |
| Deployment directory | `/opt/docker/feederhub` |
| SQLite database | `/opt/docker/feederhub/config/feederhub/feederhub.db` |
| Container UID/GID | `65532:65532` |
| Optional Garage bucket | `feederhub` |
| Vault input prefix | `vault_feederhub_` |

Preserve these storage names when changing deployment metadata.

## Networking

Kibble uses host networking for LAN-reachable WebRTC, UDP discovery, and the
broker at `127.0.0.1:1883`. Traefik routes to its host port through
[services-mini.yml.j2](../traefik/templates/traefik/dynamic/services-mini.yml.j2).
It does not use the normal proxy-network Docker-label route.

The role creates macvlan interfaces for the ONVIF devices listed in
`kibble_onvif_devices`. Each device has its own IP and MAC address on the
configured bridge. The list also supports test aliases; do not infer the
number of physical feeders from the number of interfaces.

Kalay runs in-process when `kibble_kalay_enabled` is true and binds UDP 10001
and 10240. The role stops an existing `kalay-mock.service` to avoid a port
conflict. Petlibro contains the remaining removal tasks for the old service
and `/opt/kalay-mock`. The current roles do not install an external Kalay mock
as a fallback.

## Credentials and authentication

Create `group_vars/kibble/vault.yml` with `ansible-vault create`; use
`make edit-vault FILE=group_vars/kibble/vault.yml` for subsequent changes.

| Inputs | Use |
| --- | --- |
| `vault_feederhub_registry_username`, `vault_feederhub_registry_password` | Registry deploy token with `read_registry` access |
| `vault_feederhub_feeders` | Feeder IDs, UIDs, and names expected by the application |
| `vault_feederhub_tutk_server`, `vault_feederhub_tutk_username`, `vault_feederhub_tutk_password` | TUTK settings; the in-process Kalay mode controls the emitted server endpoint |
| `vault_feederhub_oidc_client_id` | Enables native OIDC configuration |
| `vault_feederhub_oidc_client_secret` | Optional confidential web-client secret |
| `vault_feederhub_oidc_native_client_id` | Optional separate native client |

The public PocketID client uses these callbacks:

- `https://cat.atelier.house/api/auth/callback`
- `kibble://oauth-callback`

Without an OIDC client ID, the role omits the application's OIDC configuration.
Confirm the intended authentication settings before exposing the service.

## Deployment

The image is published by application CI. `kibble_image_tag` defaults to
`latest`; set it to an available commit tag for a deployment freeze or
compatible rollback.

From the repository root:

```sh
make -C deploy syntax STACK=kibble
make -C deploy kibble
```

Use [Komodo Resource Sync](../../komodo/README.md) for the Stack resource.
Its server is `Atelier`, its resource name is `kibble`, and its directory is
`/opt/docker/feederhub`. Application CI uses `KOMODO_KIBBLE_STACK=kibble` along
with its own Komodo API credentials. Static stack polling and automatic
updates are disabled; CI can explicitly request a redeployment.

After a deployment, verify application login, feeder MQTT traffic, camera
streams, and ONVIF device reachability.

## Optional photo storage

Kibble uses its own Garage instance. The S3 endpoint is published on loopback
for the host-network application. Configure
`vault_feederhub_garage_rpc_secret`, deploy, and run the staged
`/opt/docker/feederhub/garage_bootstrap.sh` on the host.

Store the generated key as `vault_feederhub_s3_access_key_id` and
`vault_feederhub_s3_secret_access_key`, then redeploy. The Garage services are
gated on the RPC secret; a deployment without it has no photo storage.
