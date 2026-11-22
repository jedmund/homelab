# Gluetun

Shared ProtonVPN tunnel on nuc-mini for the media download clients:
[qBittorrent](../qbittorrent/), [SABnzbd](../sabnzbd/), and [slskd](../slskd/).
Each client runs in its own stack with `network_mode: container:gluetun`, so it
has no network except gluetun's and no route out except the tunnel. Prowlarr,
the Starr apps, Stereo, and Qui stay off the VPN and reach the clients through
gluetun. The [granblue](../granblue/) stack runs a separate tunnel.

| Client | Shared network address | Host port | Forwarded port |
| --- | --- | --- | --- |
| qBittorrent | `http://qbittorrent:8090` | 8080 | Second (higher) port, set by its port sync |
| SABnzbd | `http://sabnzbd:8080` | 8085 | None |
| slskd | `http://slskd:5030` | 5030 | First (lower) port, set by its VPN integration |

gluetun joins the shared network with the clients' names as aliases and
publishes their web ports. Traefik's `sab.` and `sl.` routes and anything
using `<nuc-mini>:<host port>` are unchanged. qBittorrent's web UI moved from
8080 to 8090 inside the namespace because SABnzbd also listens on 8080, so any
application that uses the `qbittorrent` container name needs port 8090.

## Port forwarding

Proton forwards ports only on its P2P servers (`PORT_FORWARD_ONLY=on`) and
assigns random port numbers, which usually change when the tunnel reconnects.
gluetun requests two ports (`gluetun_forwarded_ports_count`) and renews them
every 45 seconds. It lists them in ascending order:

- slskd polls `GET /v1/portforward` on gluetun's control server and applies
  the first port as its Soulseek listener without reconnecting. It waits for
  the tunnel and the port before connecting to Soulseek, and disconnects if
  gluetun stops answering.
- `qbittorrent-port-sync` in the qBittorrent stack polls the same route every
  30 seconds and sets qBittorrent's listening port to the second port. It is
  healthy only while the two match.

Inbound peer traffic arrives through the tunnel, so the old host ports 6882
and 50300 are no longer published. Router port forwards for them are unused.

The control server listens on `127.0.0.1:8000` inside the namespace.
`config/auth/config.toml` gives the API key access to
`GET /v1/portforward` and `GET /v1/publicip/ip` only; other routes are refused.

## Image

`gluetun_image` is `qmcgaw/gluetun:latest`, upstream's main-branch build.
Multi-port forwarding for ProtonVPN (`VPN_PORT_FORWARDING_PORTS_COUNT`) is not
in v3.41.3 or the v3.41.4 release candidates. A deploy with the shared
`always` pull policy updates the image, and a new image recreates gluetun and
then all three clients, interrupting their transfers. The last verified build is revision
`eb3c7ec79d9429b9b3e3185eccde7a4806f61179`, image index digest:

```text
qmcgaw/gluetun@sha256:3c43ec327d7ab2b5f1dc798b92a7640de9a1e1b74a81c9a5143adb383c03d28b
```

To roll back, set `gluetun_image` to that reference and redeploy. A release
that contains multi-port forwarding can replace the floating tag. A pinned
release without it forwards a single port: set
`gluetun_forwarded_ports_count: 1`, and the port goes to slskd while
qBittorrent's port sync reports no port.

## Network namespace

A client joins the namespace gluetun has when the client is created. If
gluetun is recreated or restarted, the client keeps a namespace with only a
loopback interface until it is recreated. Each client's health check probes
gluetun's health server at `127.0.0.1:9999`, so a stranded client, or one
whose tunnel is down, reports `unhealthy`.

The gluetun role waits for gluetun to become healthy, then compares each
client's network mode and network namespace with gluetun's and recreates any
client stack that differs (`gluetun_clients`). A redeploy or restart from
Komodo, or a gluetun crash, does not do this. Afterward run
`make -C deploy gluetun`, or recreate the client stacks. Stopped clients that
still reference the current gluetun container are left stopped; start them
by deploying their roles.

Behavior after a host or Docker daemon restart has not been verified. If a
client is unhealthy afterward, run `make -C deploy gluetun`, then deploy the
client roles.

Each client role checks that gluetun is running before deploying, so a check
mode run of a client fails on a host where gluetun is not running yet.

## Prerequisites

1. In the Proton account, create a WireGuard configuration: VPN → WireGuard
   configuration, platform GNU/Linux, NAT-PMP (Port Forwarding) on, Moderate
   NAT off. Proton does not allow both. Name it `nuc-gluetun-media`. Only
   `PrivateKey` is used; `Address` must be `10.2.0.2/32`. gluetun chooses
   servers itself, so `[Peer]` is ignored.
2. Add the inputs in [Secrets](../../docs/secrets.md#groupvarsgluetunvaultyml)
   to `group_vars/gluetun/vault.yml`. The control server API key is read by the
   gluetun, qBittorrent, and slskd roles; nuc-mini is in all three groups.
   Generate it with `openssl rand -hex 32`.
3. In qBittorrent, enable Tools → Options → Web UI → Bypass authentication for
   clients on localhost. The port sync calls the API from `127.0.0.1` without
   credentials. Every container in the namespace (SABnzbd, slskd, the port
   sync, and gluetun) then has unauthenticated access to qBittorrent's API.

## First deployment

The clients currently publish 8080, 8085, and 5030 and hold the
`qbittorrent`, `sabnzbd`, and `slskd` names on the shared network. Stop them
before gluetun takes the ports and aliases, then deploy the clients into its
namespace:

```sh
make -C deploy check STACK=gluetun
ssh nuc 'for s in qbittorrent sabnzbd slskd; do docker compose --project-directory /opt/docker/$s stop; done'
make -C deploy gluetun
make -C deploy qbittorrent
make -C deploy sabnzbd
make -C deploy slskd
```

Then change the port of the qBittorrent download client from 8080 to 8090 in
every application that uses `http://qbittorrent:8080` (check Sonarr, Radarr,
Lidarr, Prowlarr, and Stereo). Applications that use host port 8080 are
unaffected.

## Verification

```sh
ssh nuc 'docker inspect gluetun qbittorrent qbittorrent-port-sync sabnzbd slskd --format "{{.Name}} {{.State.Health.Status}}"'
ssh nuc 'docker logs gluetun 2>&1 | grep -E "ports forwarded|public IP"'
ssh nuc 'docker exec qbittorrent curl -fsS https://ipinfo.io/ip'
ssh nuc 'docker logs --tail 5 qbittorrent-port-sync'
ssh nuc 'docker exec slskd sh -c "wget -qO- --header \"X-API-Key: \${SLSKD_API_KEY##*;}\" http://127.0.0.1:5030/api/v0/application"' | grep -o '"vpn":{[^}]*}'
```

Every container reports `healthy`. gluetun logs two forwarded ports and a
Proton address, and qBittorrent's exit address matches it. The port sync logs
the listening port it set. slskd reports `"isReady":true` for the VPN.

Stopping gluetun (`docker stop gluetun`) must leave the clients without
network access; `docker exec qbittorrent curl -m 5 https://ipinfo.io/ip`
fails. Start it again with `make -C deploy gluetun`, which also recreates the
clients.
