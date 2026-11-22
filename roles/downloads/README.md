# Downloads

The media download clients on nuc-mini and the ProtonVPN tunnel they use:
qBittorrent, SABnzbd, and slskd behind gluetun. All run in one Compose stack,
`downloads`, at `/opt/docker/downloads`. The clients use `network_mode: service:gluetun`, so
they have no network except gluetun's and no route out except the tunnel.
Prowlarr, the Starr apps, Stereo, and Qui stay off the VPN and reach the
clients through gluetun. The [granblue](../granblue/) stack runs a separate
tunnel. SABnzbd's setup and operation are in [SABnzbd](sabnzbd.md).

| Client | Shared network address | Host port | Forwarded port | Data |
| --- | --- | --- | --- | --- |
| qBittorrent | `http://qbittorrent:8090` | 8090 | Second (higher), set by `qbittorrent-port-sync` | `/opt/docker/qbittorrent/config` |
| SABnzbd | `http://sabnzbd:8080` | 8085 | None | `/opt/docker/sabnzbd/` |
| slskd | `http://slskd:5030` | 5030 | First (lower), set by its VPN integration | `/opt/docker/slskd/config` |

gluetun joins the shared network with the clients' names as aliases and
publishes their web ports. Traefik's `sab.` and `sl.` routes use host ports
8085 and 5030. Qui joins the shared network to reach qBittorrent by name.

qBittorrent's web UI is on 8090 because SABnzbd listens on 8080 in the same
namespace. The host port is also 8090: qBittorrent answers 401 to any request
whose `Host` header names a port other than the one it listens on.

## Port forwarding

Proton forwards ports only on its P2P servers (`PORT_FORWARD_ONLY=on`) and
assigns random port numbers, which usually change when the tunnel reconnects.
gluetun requests two ports (`gluetun_forwarded_ports_count`) and renews them
every 45 seconds. It lists them in ascending order:

- slskd polls `GET /v1/portforward` on gluetun's control server and applies
  the first port as its Soulseek listener without reconnecting. It waits for
  the tunnel and the port before connecting to Soulseek, and disconnects if
  gluetun stops answering.
- `qbittorrent-port-sync` polls the same route every 30 seconds and sets
  qBittorrent's listening port to the second port, re-applying it after a
  qBittorrent restart. It is healthy only while the two match.

Proton maps the second port to internal port 56789, and gluetun redirects that
to the external port number, so each client listens on the port peers see.
Inbound peer traffic arrives through the tunnel; host ports 6882 and 50300 are
not published.

The control server listens on `127.0.0.1:8000` inside the namespace.
`config/auth/config.toml` gives the API key access to `GET /v1/portforward`
and `GET /v1/publicip/ip` only; other routes are refused.

## Network namespace and recovery

A client keeps the network namespace it joined when it started. When gluetun
is recreated or restarted, the old namespace is left with only a loopback
interface, so the client must be recreated or restarted as well:

| gluetun event | Handled by |
| --- | --- |
| Recreated by Compose (new image, configuration change, redeploy) | `depends_on` with `restart: true`: Compose recreates the clients |
| Restarted by Compose (`docker compose restart`) | `depends_on` with `restart: true`: Compose restarts the clients |
| Restarted by Docker and running again (process exit with the restart policy, `docker restart gluetun`) | deunhealth: the clients' health checks fail and it restarts them |
| Stopped, or still down when deunhealth acts (crash loop, `docker stop`) | Nothing until the next `docker compose up`: a client restart fails while gluetun is not running, and the client stays exited |

The first two rows and the last two were tested with disposable containers on
nuc-mini (Docker 29.10). Komodo redeploys and restarts run Compose, so they
should follow the first two rows; that is inferred, not tested. After fixing a
gluetun that will not stay up, redeploy the stack (`make -C deploy downloads` or
Komodo) to start the clients.

Each client's health check requires `eth0` in `/proc/net/dev`, which a
stranded client no longer has. deunhealth restarts containers labeled
`deunhealth.restart.on.unhealthy=true` when their health check fails for any
reason, including an unresponsive web UI; with the shared health check
settings this takes about one and a half minutes. The port sync is labeled
too: stranded, it cannot reach gluetun's control server and its health check
fails. deunhealth mounts the Docker socket, which gives it full control of the
Docker daemon; `:ro` on the mount does not restrict the API.

gluetun reconnects the tunnel inside the container without restarting it, so a
tunnel outage does not strand the clients. Behavior after a host reboot or a
Docker daemon restart has not been verified.

## Image

`gluetun_image` is `qmcgaw/gluetun:latest`, upstream's main-branch build.
Multi-port forwarding for ProtonVPN (`VPN_PORT_FORWARDING_PORTS_COUNT`) is not
in v3.41.3 or the v3.41.4 release candidates. A deploy with the shared `always`
pull policy updates the image, and a new image recreates gluetun and then all
three clients, interrupting their transfers. The last verified build is
revision `eb3c7ec79d9429b9b3e3185eccde7a4806f61179`, image index digest:

```text
qmcgaw/gluetun@sha256:3c43ec327d7ab2b5f1dc798b92a7640de9a1e1b74a81c9a5143adb383c03d28b
```

To roll back, set `gluetun_image` to that reference and redeploy. A release
that contains multi-port forwarding can replace the floating tag. A pinned
release without it forwards a single port: set
`gluetun_forwarded_ports_count: 1`, and the port goes to slskd while
qBittorrent's port sync reports no port.

The clients use floating `latest` tags. Each service's
`homelab.config-checksum` label holds the checksums of its env and mounted
files, so a configuration change recreates only that service; a gluetun change
recreates every client.

## Prerequisites

1. In the Proton account, create a WireGuard configuration: VPN → WireGuard
   configuration, platform GNU/Linux, NAT-PMP (Port Forwarding) on, Moderate
   NAT off. Proton does not allow both. Only `PrivateKey` is used; `Address`
   must be `10.2.0.2/32`. gluetun chooses servers itself, so `[Peer]` is
   ignored.
2. Add the inputs in [Secrets](../../docs/secrets.md#groupvarsdownloadsvaultyml)
   to `group_vars/downloads/vault.yml`. Generate the control server API key with
   `openssl rand -hex 32`. The slskd credentials stay in
   [group_vars/slskd/vault.yml](../../docs/secrets.md#groupvarsslskdvaultyml);
   the `slskd` inventory group exists only to load that file.
3. In qBittorrent, enable Tools → Options → Web UI → Bypass authentication for
   clients on localhost. The port sync calls the API from `127.0.0.1` without
   credentials. Every container in the namespace then has unauthenticated
   access to qBittorrent's API.

## Deployment

```sh
make -C deploy check STACK=downloads
make -C deploy downloads
```

This stack was previously the `gluetun` Compose project in
`/opt/docker/gluetun`, with the same container names. When the role finds that
project's `compose.yaml`, it stops the project and removes the directory. Its
contents (env files, the control server roles, the port sync script, gluetun's
server list) are regenerated here; the clients' data directories are
unaffected. Komodo's Resource Sync does not delete resources, so remove the
`gluetun` stack in Komodo by hand without destroying containers.

Applications that connect to qBittorrent use port 8090: Sonarr, Radarr,
Lidarr, Prowlarr, and Stereo as `http://qbittorrent:8090`, and Qui as well
after its deployment adds it to the shared network.

## Verification

```sh
ssh nuc 'docker inspect gluetun qbittorrent qbittorrent-port-sync sabnzbd slskd deunhealth --format "{{.Name}} {{.State.Status}} {{.State.Health.Status}}"'
ssh nuc 'docker logs gluetun 2>&1 | grep -E "ports forwarded|Public IP"'
ssh nuc 'docker exec qbittorrent curl -fsS https://ipinfo.io/ip'
ssh nuc 'docker logs --tail 5 qbittorrent-port-sync'
ssh nuc 'docker exec slskd sh -c "wget -qO- --header \"X-API-Key: \${SLSKD_API_KEY##*;}\" http://127.0.0.1:5030/api/v0/application"' | grep -o '"vpn":{[^}]*}'
```

Every client reports `healthy`. gluetun logs two forwarded ports and a Proton
address, and qBittorrent's exit address matches it. The port sync logs the
listening port it set. slskd reports `"isReady":true` for the VPN.

To check recovery, run `docker restart gluetun`. The clients lose network
access until deunhealth restarts them, then report `healthy` again with
Proton's exit address.
