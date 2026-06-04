# petlibro troubleshooting

## Architecture and dependency graph

```
PetLibro PLAF203 feeder
    │
    ├── MQTT (TCP :1883) ──────────→ petlibro-mosquitto (container)
    │       reached via DNS rewrite       │
    │       mqtt.us.petlibro.com →        ├── feederhub subscribes (host net)
    │       192.168.1.6                   └── catbro subscribes (opt-in)
    │
    └── Kalay/TUTK ────────────────→ kalay-mock.service (systemd, host)
            UDP :10001/:10240               │
            TCP :10080                      ├── feederhub dials
            reached via UDM NAT             │   (FEEDERHUB_TUTK_SERVER=192.168.1.6:10001)
            (real-cloud IPs → .6)           └── catbro's embedded go2rtc dials (opt-in)
                                                (--go2rtc-tutk-server)
```

Two **manual** redirects keep feeders pointed at the local stack instead of
the real Petlibro cloud:

- DNS rewrite for `mqtt.us.petlibro.com` → `192.168.1.6` (UDM / AdGuard)
- UDM destination-NAT for the real Kalay master IPs UDP `:10001` →
  `192.168.1.6:10001` (rules listed in `mock_kalay.py` docstring)

Neither is managed by Ansible. If the UDM is reset or its config is wiped,
both must be re-applied by hand.

## Incident: 2026-06-03 — video feeds dead after NVMe swap

### Symptoms

- WebRTC offers from HA / browser clients fail with:
  ```
  webrtc/offer: streams: petlibro/tutk: dial: read udp [::]:NNNNN: i/o timeout
  ```
  Different ephemeral source port per stream — that's `net.Dial("udp", ...)`
  picking a fresh local socket per session.
- MQTT autodiscovery, feeding schedule, manual feeds — all still work.
- `petlibro-mosquitto` healthy.
- Feeders ping fine, ARP entries `REACHABLE`.

### Root cause

`mock_kalay.py` was running as a hand-launched Python process via
`/opt/kalay-mock/start.sh` with no systemd unit, no cron, no nohup state —
just a manual invocation in a tmux that didn't survive the reboot from
the NVMe swap.

The 38-hour outage parked the feeders' TUTK sessions in a backoff /
"give up" state at the firmware level. Bringing kalay_mock back online
was necessary but not sufficient — feeders had to be power-cycled to
re-attempt Kalay registration.

### What didn't cause it (but looked like it might)

These dead-ends are worth knowing so the next debugger doesn't relitigate:

1. **UFW + Docker iptables wipe.** A UFW port was re-added via Ansible
   during the swap cleanup. `ufw reload` *can* flush Docker's NAT and
   FORWARD chains, breaking outbound NAT for containers. We checked:
   `iptables -t nat -L DOCKER`, `iptables -t nat -L POSTROUTING`, and
   `iptables -L FORWARD` all had the expected rules and 88G+ of traffic
   had flowed through. Not the cause this time, but a real failure mode
   to remember.
2. **The Thunderbolt NIC's `nvmeXsX` change.** PCI re-enumeration after
   the disk swap renamed `enp87s0`, which was `DOWN` with `NO-CARRIER`.
   Not on any path the petlibro stack uses; default route is `br0`,
   camera VLAN trunks on `enp5s0.20`.
3. **catbro being disabled.** Catbro is opt-in for protocol research
   (`--mode record`) and is a *consumer* of TUTK via
   `--go2rtc-tutk-server 192.168.1.6:10001`, not a provider. Re-enabling
   it added another go2rtc instance fighting feederhub for :8554/:8555
   but did not restore the missing :10001 endpoint.

## Diagnostic playbook

Run these in order on `nuc`. Each step narrows where the break is.

```bash
# 1. Container layer
docker ps --filter "name=petlibro" --format "table {{.Names}}\t{{.Status}}"
docker ps --filter "name=feederhub" --format "table {{.Names}}\t{{.Status}}"
docker logs petlibro-mosquitto --tail 20

# 2. kalay_mock service
systemctl status kalay-mock.service
sudo ss -ulnp | grep -E ":10001|:10240"
sudo ss -tlnp | grep ":10080"

# 3. kalay_mock activity — these two log lines are the smoke test
sudo tail -f /opt/kalay-mock/mock.log
#   want to see, within ~30s:
#     [192.168.1.180:NNNNN] KEEPALIVE uid=JNGT5PBUAF61NKVS111A    (feeder is alive)
#     [192.168.1.181:NNNNN] KEEPALIVE uid=HFEY837GWWHWC27U111A    (feeder is alive)
#     [192.168.1.6:NNNNN] GET_RIP uid=...                          (feederhub is polling)

# 4. Feeder reachability
ping -c 2 192.168.1.180
ping -c 2 192.168.1.181
ip neigh show | grep -E "192\.168\.1\.18[01]"

# 5. MQTT — do feeders have live TCP sessions to mosquitto?
sudo ss -tnp | grep -E "192\.168\.1\.18[01]"
#   should show ESTABLISHED on :1883

# 6. Wire-level — what are the feeders actually emitting?
sudo timeout 15 tcpdump -i any -nn "(host 192.168.1.180 or host 192.168.1.181) and not arp"
#   healthy: TCP :1883 (MQTT) + UDP :10001/:10240 (TUTK keepalives)
#   broken-tutk: only TCP :1883
```

## Recovery

### Case A: kalay-mock down, feeders otherwise healthy

```bash
sudo systemctl start kalay-mock
sudo ss -ulnp | grep 10001    # verify bind
sudo tail -f /opt/kalay-mock/mock.log
```

If the unit isn't installed at all (post-reimage):

```bash
cd ~/Developer/Personal/homelab
ansible-playbook deploy/petlibro.yml
```

The role's handlers copy the scripts to `/opt/kalay-mock/`, template the
unit at `/etc/systemd/system/kalay-mock.service`, daemon-reload, and
start the service.

### Case B: feeders TUTK-silent (MQTT works, no UDP keepalives)

This is what the 2026-06-03 incident looked like after kalay-mock was
restored. The feeders' firmware has parked TUTK; they need a kick:

1. Unplug each feeder for ~10 seconds.
2. Plug back in.
3. Watch `/opt/kalay-mock/mock.log` — KEEPALIVE entries from
   `192.168.1.180` and `.181` should appear within ~30s, then GET_RIPs
   from `192.168.1.6` should start hitting them, then video flows.

If the feeders come back with different DHCP-assigned IPs, the
`--seed-feeder` args in the unit are now wrong. Update `local_ip` for
each entry in `petlibro_feeders` (in `roles/petlibro/defaults/main.yml`)
and redeploy. Static DHCP reservations on the UDM prevent this.

### Case C: feeders unreachable (no ping, no ARP)

Check the IoT VLAN / switch port / power. Not in scope of this stack.

### Case D: DNS or UDM NAT rewrite missing

If the UDM was reset:

- Add DNS rewrite for `mqtt.us.petlibro.com` → `192.168.1.6`.
- Re-add destination-NAT rules from the `mock_kalay.py` docstring
  (real Kalay master IPs UDP `:10001` → `192.168.1.6:10001`, etc.).
- Then power-cycle the feeders.

## Lessons baked into the Ansible role

- `kalay_mock` is a host-level systemd unit owned by `roles/petlibro/`
  rather than a hand-launched script. Survives reboots, restartable
  via `systemctl`, logs to both journald and `/opt/kalay-mock/mock.log`.
- Seed feeders for the unit are rendered from the same `petlibro_feeders`
  list that drives `creds.toml` and `go2rtc.yaml`, so adding/renaming a
  feeder updates everything from one place — but the `local_ip` field
  must be kept honest.
- The UDM NAT rules and DNS rewrite are still manual and still load-
  bearing. Documented in `README.md` under "Manual prerequisites".
