# kibble role

Compose stack on `nuc-mini` for kibble — the Go service that
bridges a pair of PetLibro PLAF203 cat feeders into Home Assistant
and serves a SvelteKit UI for live event + camera views.

Image is built by GitLab CI in
[`jedmund/kibble`](https://git.atelier.house/jedmund/kibble)
and pushed to
`registry.atelier.house/jedmund/kibble:{<sha>,<branch-slug>,latest}`.
On successful main builds, CI also calls the Komodo API to redeploy
this stack — so merging an MR is the deploy.

| Service | Domain | Networking |
|---|---|---|
| kibble | `cat.atelier.house` | **host network** (see below) |

## Why `network_mode: host`

Three reasons kibble doesn't sit on the standard proxy/backend
bridges:

1. **WebRTC ICE candidates** must advertise an address the browser
   can reach.  In bridge mode go2rtc would advertise the docker
   bridge IP — unreachable from LAN clients.
2. **UDP discovery surfaces** (TUTK, the WebRTC media plane) bind
   to every interface go2rtc can see.  On a bridge network that's
   only the docker bridge.
3. **MQTT** points at `tcp://127.0.0.1:1883` — the host port the
   `petlibro-mosquitto` container in `roles/petlibro/` publishes.
   No need to share a Compose network between the two stacks.

Cost: Traefik can't auto-discover via the docker provider (no
shared network).  Mitigated by a router + service block in
`roles/infra_gateway/templates/traefik/dynamic/services-mini.yml.j2`
(search for `kibble`).

## Kalay: self-hosted in-process

Kibble runs its own Kalay master (`internal/kalay`) when
`kibble_kalay_enabled: true` (the default).  It binds UDP 10001 +
10240 under `network_mode: host` and impersonates ThroughTek's cloud,
so feeders register locally and the video plane dials them directly —
**no external `kalay-mock` unit required**.  Relevant vars in
`defaults/main.yml`:

- `kibble_kalay_host_lan_ip` — the nuc's LAN IP, advertised to
  feeders and used as the PUNCH_TO2 source (defaults to the ONVIF
  advertise host).
- `kibble_feeder_ips` — `uid → LAN IP` seeds so `GET_RIP` answers on
  boot instead of after the first KEEPALIVE.
- `KIBBLE_TUTK_SERVER` is emitted blank while Kalay is on, so the
  binary auto-targets its own `127.0.0.1:10001` listener.

Because kibble and the old `kalay-mock` would collide on those UDP
ports, this role stops + disables `kalay-mock.service` on deploy, and
`roles/petlibro/` gates it behind `petlibro_kalay_mock_enabled: false`.
To fall back to the external mock, set `kibble_kalay_enabled: false`
here and `petlibro_kalay_mock_enabled: true` there.  See
`roles/petlibro/TROUBLESHOOTING.md` for the recovery playbook.

## Required vault entries

`group_vars/kibble/vault.yml` (encrypted) must define:

```yaml
vault_feederhub_tutk_server: kalay-cloud.tutk.com
vault_feederhub_tutk_username: <kalay-account-username>
vault_feederhub_tutk_password: <kalay-account-password>
vault_feederhub_feeders: "<device_id>:<uid>:<name>,<device_id>:<uid>:<name>"

# GitLab deploy token scoped to read_registry.
vault_feederhub_registry_username: gitlab+deploy-token-N
vault_feederhub_registry_password: <token>

# Kibble's dedicated Garage instance.
vault_feederhub_garage_rpc_secret: <32-byte-hex-secret>
vault_feederhub_s3_access_key_id: <garage-access-key>
vault_feederhub_s3_secret_access_key: <garage-secret-key>

# PocketID. The secret and separate native client are optional.
vault_feederhub_oidc_client_id: <public-client-id>
vault_feederhub_oidc_client_secret: <optional-confidential-client-secret>
vault_feederhub_oidc_native_client_id: <optional-ios-client-id>

# ONVIF camera authentication.
vault_feederhub_onvif_user: <onvif-user>
vault_feederhub_onvif_pass: <onvif-password>
```

Create with `make edit-vault FILE=group_vars/kibble/vault.yml`.

The first Garage deploy can start with only
`vault_feederhub_garage_rpc_secret`. Run
`/opt/docker/feederhub/garage_bootstrap.sh`, copy the generated S3 key pair
into the vault, and redeploy. Register the PocketID client with both callback
URLs from `defaults/main.yml` before enabling OIDC.

## Komodo Stack setup (one-time, manual)

After the first `make deploy-kibble` brings up the stack:

1. In Komodo at `https://ko.atelier.house`, create a Stack resource:
   - Name: `kibble`
   - Server: `nuc-mini`
   - Files on host: **enabled**
   - Project source: `/opt/docker/feederhub`
   - Compose file: `compose.yaml`
   - Polling / auto-update: **disabled** (CI is the trigger).
2. Generate an API key + secret.
3. Set CI variables in the `jedmund/kibble` GitLab project
   (Settings → CI/CD → Variables, masked + protected):
   ```
   KOMODO_URL=https://ko.atelier.house
   KOMODO_API_KEY=<from step 2>
   KOMODO_API_SECRET=<from step 2>
   KOMODO_KIBBLE_STACK=kibble
   ```

After that, merging an MR to `main` in jedmund/kibble fires
`check → build:image → deploy:komodo` and the new image is live
within ~3 min.

## Deploying / rolling forward by hand

Auto-deploy is the normal path.  To force-roll forward (e.g. after
a vault edit) or pin to a specific sha:

```bash
# Bump tag and run the playbook.
$EDITOR roles/kibble/defaults/main.yml   # change kibble_image_tag
make deploy-kibble
```

## Where the data lives

- `/opt/docker/feederhub/config/feederhub/feederhub.db` — SQLite
  state (events, schedules, feeders).  On-disk paths keep the
  `feederhub` name (see `data_name` in defaults) so the rename did not
  migrate the DB or Garage volumes.  Distroless container runs as
  uid 65532; this dir must be owned by it.
