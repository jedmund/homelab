# petlibro

Local Mosquitto broker for PLAF203 feeders, a kalay_mock systemd unit that
provides the local TUTK relay on `:10001`, plus an opt-in catbro-server
container for protocol research.

Runs on `nuc-mini` (NUC15). Home Assistant on NUC8 connects to it over MQTT.

When something breaks, see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — has
the dependency graph, diagnostic playbook, and the 2026-06-03 NVMe-swap
postmortem.

## What this deploys

By default, **one container** at `/opt/docker/petlibro/` plus **one
host-level systemd unit**:

- **mosquitto** (container) — Eclipse Mosquitto 2.x, anonymous, listening on
  `1883`.  Both feeders (via DNS rewrite) and HA-on-NUC8 connect here.
- **kalay_mock** (systemd unit) — Python re-implementation of the Kalay
  master server.  Binds UDP `:10001` + `:10240` and TCP `:10080` on the host;
  feederhub's `FEEDERHUB_TUTK_SERVER=192.168.1.6:10001` dials it for the
  video plane.  Lives on the host (not in Docker) because it pre-dated the
  containerised stack and the scripts have always run directly under Python.

The MQTT bridge / feeding-schedule plane is owned by **feederhub**
(`roles/feederhub`).  Catbro is opt-in for protocol-capture sessions; see
"Enabling catbro" below.

### catbro-server (opt-in, default off)

When enabled, adds a second container built locally from
[bobobo1618/catbro-server](https://github.com/bobobo1618/catbro-server)
(Rust + embedded
[bobobo1618/go2rtc](https://github.com/bobobo1618/go2rtc) Go fork). Acts as
the Petlibro MQTT cloud; embeds go2rtc with the `pkg/tutk/`
reimplementation that speaks PLAF203 video directly. Exposes RTSP on `8554`
and a WebUI on `1984`.

Catbro's remaining purpose post-feederhub is **protocol research**: its
`--mode record` writes every observed MQTT frame to a JSONL log file, which
is how we found `DEVICE_LOG_REPORT_EVENT` carries the Kalay UID, the real
`MANUAL_FEEDING_SERVICE` cmd, etc.  Enable for capture sessions, then disable
so it stops fighting feederhub for `:8554` / `:8555` / `:1984`.

### Enabling catbro

Set `petlibro_catbro_enabled: true` (group/host vars or `-e`) and re-run the
playbook:

```bash
ansible-playbook deploy/petlibro.yml -e petlibro_catbro_enabled=true
```

To disable again (the usual state):

```bash
ansible-playbook deploy/petlibro.yml -e petlibro_catbro_enabled=false
```

The `remove_orphans: true` flag on the compose task tears down the running
catbro container when the flag flips back to false.

Ports exposed on NUC15:

| Port | Protocol | Owner | Purpose |
|---|---|---|---|
| 1883 | TCP | mosquitto | MQTT broker (feeders + HA both connect) |
| 10001 | UDP | kalay_mock | Kalay master server (primary) |
| 10240 | UDP | kalay_mock | Kalay master server (alt port used by some feeders) |
| 10080 | TCP | kalay_mock | Kalay-over-TCP for AV streaming |
| 1984 | TCP | catbro (opt-in) | go2rtc WebUI / HTTP API |
| 8554 | TCP | catbro (opt-in) | RTSP streams (HA cameras source from here) |
| 8555 | TCP | catbro (opt-in) | WebRTC TCP fallback |

### kalay_mock

Host systemd unit (`/etc/systemd/system/kalay-mock.service`) running
`python3 mock_kalay.py` out of `/opt/kalay-mock/`.  Scripts live in
`roles/petlibro/files/kalay-mock/` and are copied byte-for-byte from
[`PetLibro/feeder-re/mock-kalay/`](https://github.com/jedmund/petlibro)
— update there first, then resync via this role.

Seed feeders for the registry come from `petlibro_feeders` (the same list
that drives creds.toml + go2rtc); each entry needs a `local_ip` field so
the mock can answer UID lookups before the feeder's first KEEPALIVE.

Logs append to `/opt/kalay-mock/mock.log`; `journalctl -u kalay-mock` also
works.  Verify with `sudo ss -ulnp | grep 10001` after deploy.

## Manual prerequisites (deliberately NOT automated)

### 1. DNS rewrite for `mqtt.us.petlibro.com` → NUC15

In UDM / AdGuard / whatever DNS the IoT VLAN resolves through, override
`mqtt.us.petlibro.com` to point at the NUC15 LAN IP (`192.168.1.6` at time of
writing). Without this, feeders connect to the real Petlibro cloud and our
local mosquitto + kalay_mock never see them.

UDM controller path: Settings → Networks → iot.local → DHCP Settings → Custom
DHCP options OR via the Site Manager DNS overrides. AdGuard alternative: add a
DNS rewrite for `mqtt.us.petlibro.com` → `192.168.1.6`.

### 2. Power-cycle the feeders after first deploy

Feeders cache their resolved MQTT IP. After flipping the DNS rewrite, unplug
each feeder for 10 seconds and plug back in.

### 3. Verify with mosquitto logs

```bash
ssh nuc 'docker logs petlibro-mosquitto -f' | grep -i "new connection from"
```

You should see two `New connection from <feeder-ip>` lines within a couple of
minutes of power-up.

## Home Assistant integration (on NUC8)

### MQTT broker

Configurations → Integrations → MQTT → Configure:

- Broker: `192.168.1.6` (NUC15)
- Port: `1883`
- Username/password: leave empty (anonymous)
- Discovery: enabled
- Discovery prefix: `homeassistant` (matches catbro default)

After this, catbro's autodiscovery should surface the feeders as entities
(sensors for surplus grain, battery, motor state; switches for light, sound;
buttons for manual feed; etc. — what's published depends on what catbro
implements). Check the new entities under Settings → Devices & Services →
MQTT → "Petlibro" devices.

### Camera entities

Add to `configuration.yaml` on HA:

```yaml
camera:
  - platform: generic
    name: Left Feeder
    stream_source: rtsp://192.168.1.6:8554/petlibro_left_feeder
    still_image_url: ""

  - platform: generic
    name: Right Feeder
    stream_source: rtsp://192.168.1.6:8554/petlibro_right_feeder
    still_image_url: ""
```

(Stream names come from the `friendly_name` in `petlibro_feeders`, prefixed
with `petlibro_` per catbro's `--go2rtc-stream-prefix` default.)

Restart HA, then add a `picture-glance` card or similar for the camera.

## Deploying / updating

From the `deploy/` directory:

```bash
# Initial deploy or any change
make petlibro
# or, equivalently:
make deploy STACK=petlibro

# Dry-run
make check STACK=petlibro

# Just rebuild the catbro image (e.g., after bumping catbro_repo_ref)
make deploy STACK=petlibro EXTRA_ARGS="-t build -e force_rebuild=true"
```

First build is slow (~5-10 min): Rust + Go from scratch on the NUC. After
that, only changes to the catbro source re-trigger a build (Ansible diffs the
git revision).

## Where the data lives

- `/opt/docker/petlibro/data/mosquitto/` — MQTT persistence (retained
  messages, sessions). Safe to delete; clients republish on reconnect.
- `/opt/docker/petlibro/data/catbro/state.toml` — Per-feeder feeding plan
  state. Worth backing up if you want feeding schedules to survive a
  redeploy.
- `/opt/docker/petlibro/data/catbro/creds.toml` — Static config rendered from
  `petlibro_feeders`. Recreated on every deploy from defaults.
- `/opt/docker/petlibro/src/` — Cloned catbro source. Get rebuilt on
  `catbro_repo_ref` change.

## Configuration

The two things you'll commonly change are in
`roles/petlibro/defaults/main.yml`:

- `catbro_repo_ref` — bump this to pull in upstream catbro changes
- `petlibro_feeders` — add/remove/rename feeders here

Adding a feeder:

1. Get its `device_sn` and `tutk_uid` (`cameraId` field) from the Petlibro
   REST API via `/device/device/list`. See
   `~/Developer/Github/PetLibro/step2_get_creds.py` for the signed-request
   client.
2. Append to `petlibro_feeders` in defaults.
3. `make deploy STACK=petlibro`.
4. Power-cycle the new feeder.

## Caveats

The author of catbro-server explicitly describes the code as "vibe-coded" with
LLM assistance and offers no support. Expect rough edges. The two things most
likely to bite:

- Some MQTT message types may not be implemented yet (e.g., specific event
  attributes). The feeder may misbehave or log warnings. Check
  `docker logs petlibro-catbro` for `unparseable topic` or `unknown command`
  warnings.
- The TUTK reverse-engineering covers PLAF203 specifically. Other Petlibro
  models (PLAF301, Luma, etc.) may need their session protocol added.

If something breaks, the upstream is responsive (open an issue on
[bobobo1618/catbro-server](https://github.com/bobobo1618/catbro-server)
referencing the message type that didn't parse).
