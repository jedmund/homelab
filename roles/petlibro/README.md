# petlibro

Mock Petlibro cloud + TUTK video streaming for PLAF203 (and similar) feeders.
Replaces both Petlibro's MQTT cloud and TUTK Kalay's video plane with local
implementations. Feeders never reach the internet.

Runs on `nuc-mini` (NUC15). Home Assistant on NUC8 connects to it over MQTT and
RTSP.

## What this deploys

Two containers in one Docker compose stack at `/opt/docker/petlibro/`:

- **mosquitto** — Eclipse Mosquitto 2.x, anonymous, listening on `1883`. Both
  feeders (via DNS rewrite) and HA-on-NUC8 connect here.
- **catbro** — Built locally from
  [bobobo1618/catbro-server](https://github.com/bobobo1618/catbro-server)
  (Rust + embedded
  [bobobo1618/go2rtc](https://github.com/bobobo1618/go2rtc) Go fork). Acts as
  the Petlibro MQTT cloud; embeds go2rtc with the
  `pkg/tutk/` reimplementation that speaks PLAF203 video directly. Exposes RTSP
  on `8554` and a WebUI on `1984`.

Ports exposed on NUC15:

| Port | Protocol | Purpose |
|---|---|---|
| 1883 | TCP | MQTT broker (feeders + HA both connect) |
| 1984 | TCP | go2rtc WebUI / HTTP API |
| 8554 | TCP | RTSP streams (HA cameras source from here) |
| 8555 | TCP | WebRTC TCP fallback |

## Manual prerequisites (deliberately NOT automated)

### 1. DNS rewrite for `mqtt.us.petlibro.com` → NUC15

In UDM / AdGuard / whatever DNS the IoT VLAN resolves through, override
`mqtt.us.petlibro.com` to point at the NUC15 LAN IP (`192.168.1.6` at time of
writing). Without this, feeders connect to the real Petlibro cloud and the
local catbro never sees them.

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
