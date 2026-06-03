# utilities role

Compose stack on `nuc-mini` for general-purpose services.  Today:

| Service | Domain | Networking |
|---|---|---|
| n8n | `n8n.atelier.house` | proxy + backend bridges |
| n8n-db (Postgres 16) | — | backend bridge |
| ChangeDetection.io | `track.atelier.house` | proxy bridge |
| Copyparty | `files.atelier.house` | proxy bridge |
| feederhub | `cat.atelier.house` | **host network** (see below) |

## feederhub specifics

feederhub is a Go binary (built from
[`/Users/justin/Developer/PetLibro/feederhub`](https://git.atelier.house/jedmund/feederhub))
that bridges a pair of PetLibro PLAF203 cat feeders into Home
Assistant and serves a SvelteKit UI for live event + camera views.

It joins the utilities stack because it's a small homelab utility and
keeping it next to n8n/changedetection means one fewer Compose project
to mind.

### Why `network_mode: host`

Departure from every other service in this stack.  Three reasons:

1. **WebRTC ICE candidates** must advertise an address the browser can
   reach.  In bridge mode go2rtc would advertise the docker bridge IP
   — unreachable from LAN clients.
2. **UDP discovery surfaces** (TUTK, the WebRTC media plane) bind to
   every interface go2rtc can see.  On a bridge network that's only
   the docker bridge.
3. **MQTT** points at `tcp://127.0.0.1:1883` — the host port the
   `petlibro-mosquitto` container publishes.  No need to share a
   Compose network between the two containers.

Cost: Traefik can't auto-discover via the docker provider (no shared
network).  Mitigated by a router + service block in
`roles/infra_gateway/templates/traefik/dynamic/services-mini.yml.j2`
(search for `feederhub`).  Traefik's file provider watches
`/config/dynamic/` so picking up the new route is instant — no
restart required.

### Required vault entries

`group_vars/utilities/vault.yml` (encrypted) must define:

```yaml
feederhub_tutk_server: kalay-cloud.tutk.com         # or whatever the live host is
feederhub_tutk_username: <kalay-account-username>
feederhub_tutk_password: <kalay-account-password>
feederhub_feeders: "<device_id>:<uid>:<name>,<device_id>:<uid>:<name>"
```

Bootstrap from the existing smoke-test `.env` on the nuc:

```bash
ssh nuc-mini 'grep -E "FEEDERHUB_TUTK_|FEEDERHUB_FEEDERS" /tmp/feederhub-smoke/.env'
ansible-vault edit group_vars/utilities/vault.yml
# Paste the values without the FEEDERHUB_ prefix and with the
# `feederhub_` Ansible naming.  TUTK_SERVER → feederhub_tutk_server, etc.
```

### Image build + push

The `feederhub_image_tag` default points at a tag in
`ghcr.io/jedmund/feederhub`.  To cut a new release:

```bash
cd /Users/justin/Developer/PetLibro/feederhub
make docker-publish PUBLISH_TAG=<new-tag>
# Then bump feederhub_image_tag in defaults/main.yml and re-run the playbook.
```

See `feederhub/deploy/README.md` for prerequisites and registry login.

### Cutover from the smoke deploy

The first deploy via this role migrates feederhub off the manual
`/tmp/feederhub-smoke/` nohup process.  Order matters — port :18080
on the host is currently bound by the manual process; Compose can't
start `feederhub` until the manual one is stopped.

```bash
# 1. Preserve the events history (Phase 3 + 4 soak data).
ssh nuc-mini 'sudo mkdir -p /opt/docker/utilities/config/feederhub
              sudo cp /tmp/feederhub-smoke/feederhub.db \
                      /opt/docker/utilities/config/feederhub/feederhub.db
              sudo chown -R 65532:65532 /opt/docker/utilities/config/feederhub'

# 2. Stop the manual process (frees port :18080).
ssh nuc-mini 'sudo kill -TERM "$(pgrep -x feederhub)"'

# 3. Push a fresh image if you haven't already.
( cd ~/Developer/PetLibro/feederhub && make docker-publish PUBLISH_TAG=phase4-cameras )

# 4. Run the playbook.  ~30 s for compose pull + start.
ansible-playbook deploy/utilities.yml --tags utilities -K

# 5. Smoke.
curl -s https://cat.atelier.house/health | jq
```

The old binary backups under `/tmp/feederhub-smoke/feederhub.*` can
be removed once the new deploy soaks cleanly for ~1 hour.
