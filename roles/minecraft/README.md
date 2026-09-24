# Minecraft

Ansible owns project `minecraft` at `/opt/stacks/minecraft` on `max`. Existing
server directories, container names, mods, worlds and RCON passwords are
preserved. Game traffic bypasses Traefik; the existing `mc.atelier.house` HTTP
panel registration is independent.

| Address | Installation | NeoForge | Maximum heap / container limit |
| --- | --- | --- | --- |
| `sky.mc.atelier.house` | ATM10 To the Sky 1.8, Minecraft 1.21.1 | 21.1.215 | 16G / 20G |
| `atm10.mc.atelier.house` | All the Mods 10 5.4, Minecraft 1.21.1 | 21.1.215 | 32G / 40G |
| `vanilla.mc.atelier.house` | Existing custom modpack, Minecraft 1.21.1 | 21.1.217 | 16G / 20G |

## Prerequisites and first deployment

The role rejects missing worlds, libraries, mods, startup files, unexpected
versions, disabled account authentication or missing RCON credentials. It does
not install a new world, download modpacks, replace gameplay properties or add
an allowlist. Existing properties must use `world`, port 25565 and enabled RCON.
The RCON password is copied under `no_log` into a mode-0600 raw environment file;
RCON is never published. Original environment files remain untouched.

1. Repair and verify the existing [Borg NAS mirror](../backup/README.md#nas-mirror).
   Do not initialize another repository or replace encryption keys.
2. Confirm all three backends are stopped. Install snapshot tools without changing
   Compose or starting servers:

   ```sh
   make -C deploy deploy STACK=minecraft EXTRA_ARGS='-e minecraft_prepare_only=true'
   ```

   Then run `sudo /usr/local/sbin/minecraft-snapshot baseline` on max. This copies
   the complete three server directories, Compose and env directory to
   `/var/backup/minecraft/baseline`. Baselines have no exclusions.
3. Transfer that directory as a tar to nuc-mini. Create a named baseline archive
   in the existing Borg repository using its existing credentials. Mirror under
   `borg with-lock`, compare archive IDs, extract the tar from Borg into an
   isolated directory and compare its content to the stopped data. Verify the
   corresponding archive through the NAS repository too.
4. Only after those checks, write `/var/backup/minecraft-baseline-verified` on max
   with archive name, archive ID, verification date and baseline path. The role
   requires this operator receipt before changing Compose or starting containers.
5. Run `make -C deploy minecraft`. All backends initially remain created/stopped.
   Rerun it and compare container IDs and states to establish idempotence.
6. Configure the restricted snapshot key described below, enable backup coverage,
   then run `make -C deploy ddclient` for the three DNS-only A records and
   Minecraft SRV records.
7. Verify gateway WAN TCP `21212 -> 192.168.1.100:21212`. Configure NAT loopback or
   local DNS for LAN clients. Gateway configuration is an explicit prerequisite;
   this repository has no gateway configuration provider. The role opens TCP
   21212 in UFW. Cloudflare SRV records direct the three hostnames to port 21212,
   so clients can enter a hostname without a port suffix. Docker's published-port rules must also be considered when
   reviewing host packet filtering. The role removes the former TCP 25565
   firewall rule.

No backend port or Docker API endpoint is published. Only the socket proxy
mounts the Docker socket. Its private control network permits discovery and
start requests, with general POST access disabled. Backends have an egress-capable
Minecraft network for account authentication.

## Lifecycle and players

Join the appropriate hostname with a matching modded Minecraft client. Minecraft
SRV records direct these hostnames to public TCP port 21212, so a port suffix is
not needed. Status
polls report sleeping/loading messages without waking a server. A join starts
only the selected backend. Large modpacks take several minutes; wait and reconnect.
Unknown hostnames have no default backend.

The image's [auto-stop](https://docker-minecraft-server.readthedocs.io/en/latest/misc/autopause-autostop/autostop/)
stops an unused server after 900 seconds, with a 300-second shutdown allowance
and Compose stop grace of 360 seconds. Initial heaps are 1G. The router's own
stop function is disabled because its Docker stop timeout is shorter. Backend
restart policies are `no`; after a host boot they remain asleep until joined.
Infrastructure restarts automatically.

Routine deployment briefly closes the router, captures backend states, uses
`compose create` for sleeping services and a single normal Compose deployment
for infrastructure and previously awake services. An unchanged deployment
preserves container IDs and backend states. A configuration change can restart
an awake backend; schedule such changes outside gameplay. No generic Komodo
Stack, fleet redeploy or automatic image updater should own this project.
Image updates require editing the pinned digests and repeating the backup and
world/client verification process.

Deployment and snapshot/export operations share `/run/minecraft-maintenance.lock`.
A busy lock fails the operation; rerun after the active operation finishes.
After an interrupted controller deployment, inspect the host for active snapshot,
export or deployment processes before removing a stale lock directory. Restore
the router with `docker start minecraft-router` if required. Never clear an active
lock. `/run` clears stale locks on host boot.

## Recurring backup

The max timer checks every 15 minutes and publishes at most one snapshot every
24 hours. It defers while any backend is running, restarting or paused. It
stops only the router, checks backend state again, copies into private staging,
and atomically switches `current` only on completion. Exception handling and
systemd `ExecStopPost` restore a previously running router, including timeouts.
A host crash can leave a partial directory; it is not exported or archived.

Recurring copies exclude nested `backup`, `backups`, `simplebackups`, `world.bck*`,
logs and BlueMap web output. All original files remain in place. The initial
baseline retains these too. Snapshots include entire server directories, including
mods, configs, libraries, startup files and world dimensions/player data.

On nuc-mini, enable `backup_minecraft_enabled` only when a completed snapshot
exists and SSH export works. Set `backup_minecraft_host_key` to max's public
Ed25519 host key obtained through an already authenticated connection. Deploy
the backup role to create `/opt/docker/backup/minecraft-ssh/id_ed25519`. Pass
its `.pub` content as `minecraft_backup_public_key` when deploying Minecraft.
The key is restricted to nuc-mini's address and a fixed root snapshot-export
command, with forwarding and interactive access disabled. No encryption key
or existing credential is regenerated.

The Borg pre-create hook pulls a tar while holding the remote maintenance lock.
Failed transfers leave the previous complete local tar intact. Publication is a
single atomic rename. Borgmatic uses `/scripts/borg-locked.sh` to hold a shared
transfer lock throughout each Borg operation; publication holds it exclusively.
Use this wrapper for manual Borg archive creation too. This prevents a transfer
from triggering Borg’s changed-file checks during an archive.
The hook refuses snapshots older than 27 hours and sends failures through the
existing Borgmatic Healthchecks integration. The scheduled backup verifier checks
snapshot age separately from archive age and checks NAS divergence. Retention
remains the existing 30-day Borg policy.

On max:

```sh
sudo systemctl start minecraft-snapshot.service
sudo journalctl -u minecraft-snapshot.service --no-pager -n 30
sudo systemctl list-timers minecraft-snapshot.timer
```

For an explicit fresh copy after an idle maintenance or restore test, run
`sudo /usr/local/sbin/minecraft-snapshot refresh`. It bypasses only the daily
age gate; it still defers for awake backends and never stops a game server.

On nuc-mini:

```sh
docker exec borgmatic /scripts/pull-minecraft.sh
/opt/docker/backup/scripts/verify-backup-status.sh
```

## Restore and rollback

Select an archive containing `minecraft/snapshot.tar` (or the recorded baseline).
Extract to an isolated directory using the existing repository credentials, then
unpack the tar there. Run `roles/minecraft/files/validate-data.py <restored-root>`
and compare world files, mods, configs and startup files against that snapshot.
Confirm the matching Minecraft, NeoForge and modpack versions before startup.
This proves file recovery; a matching client must separately verify gameplay.

For production restore, stop the router and affected backends, acquire the
maintenance lock, preserve the failed directory, and restore the complete server
directory. Restore the saved Compose/env configuration for deployment rollback.
Use the verified baseline if startup changed data incompatibly. Preserve operator
lists and credentials. Release the lock, start infrastructure and wake one world
at a time. Never overwrite a running world.

## Validation

```sh
make check
python3 tests/test_minecraft.py
python3 tests/test_minecraft_transfer.py
python3 tests/test_maintenance.py
python3 ci/validation.py fast
git diff --check
```

Use Python from the Ansible environment for Jinja2/PyYAML. Before declaring
coverage complete, verify first deployment, unchanged deployment, configuration
changes, mixed awake/asleep state, boot recovery, idle shutdown, subsequent wake,
LAN and external routing, unknown-host rejection, all three matching clients,
a recurring Borg/NAS backup and an isolated restore. See [the rollout record](rollout.md) for
checks actually completed; configuration alone is not proof of service health.
