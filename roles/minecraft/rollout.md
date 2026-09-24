# Minecraft rollout record

Rollout started 2026-09-23. This record is updated as checks complete.

## Confirmed before startup

- Existing data and baseline on max match Minecraft 1.21.1 and NeoForge
  21.1.215 (sky/atm10), 21.1.217 (vanilla). All worlds and libraries exist;
  account authentication and RCON are enabled. No Minecraft containers were
  present at the start of rollout.
- The NAS mirror failed twice with NFS write timeouts at unrestricted speed.
  A lock-protected retry limited to 20000 KiB/s completed. All 54 archive
  names and IDs then matched between local Borg and NAS. The existing backup
  status verifier passed. The managed mirror holds the Borg lock throughout replication. A later
  baseline mirror failed even at that rate, so throttling alone was insufficient.
- A full stopped baseline was copied on max. A separate recurring snapshot
  was produced without waking servers. Restricted SSH export from max to
  nuc-mini succeeded.
- Backup role deployment on nuc-mini succeeded and Borgmatic configuration
  validation passed. Existing Borg image utilities supported SSH, tar, flock
  and timeout, so no backup image build was required.
- ddclient deployment succeeded and created the three DNS-only A records.
- The user confirmed gateway forwarding and local DNS configuration. After the user updated
  the wildcard override, LAN DNS at 192.168.1.1 resolved all three names to
  192.168.1.100. The Mac and max also use public DNS resolvers and still returned the WAN
  address through their normal resolver. Direct LAN transport with hostname
  routing passed. External and normal client connections remain pending.
- Live Komodo has no Minecraft Stack registration.

## Validation

The focused snapshot, transfer and maintenance suites pass. Disposable Docker
fixtures on max pass initial sleeping deployment, unchanged identity, mixed
states, configuration changes and simulated boot recovery. Real pinned router
and socket-proxy fixtures pass sleeping/loading status, status polling without
wake, selected-backend wake and unknown-host rejection. Fixtures were removed.

A concurrent pull during the custom baseline archive triggered Borg's
changed-file warning for the recurring snapshot tar. The independent baseline
tar was not changed. This exposed the need to protect archive reads as well as
publication. A shared-lock Borg wrapper was added and tested against the actual
backup container; normal recurring backup must be repeated with that wrapper
before coverage is declared complete.

`make check` passed. Fast documentation validation and whitespace checks passed.
The broader `tests/compose_lifecycle.py --static-only` suite fails at the existing
`degoog` Compose-handler assertion before reaching rendering checks; that gate
was not changed or weakened. The Minecraft Compose template was separately
rendered with placeholder credentials and accepted by Docker Compose.

## NFS repair

A later baseline mirror failed even at 20000 KiB/s. The backup mount used
`soft,timeo=30`, a three-second response timeout. The managed setting now uses
`timeo=600`, retaining bounded soft failures for the replica while allowing
normal TCP response latency. Mount maintenance checks for active backup
processes and releases Borgmatic's bind before recycling the host mount; a
running container otherwise retained the old NFS superblock and its options.
Both host and container were verified at `timeo=600`. A 512 MiB random write
with fsync completed in four seconds. The baseline mirror completed at a 50000 KiB/s limit, transferring 40.60 GB.
All 55 archive names and IDs matched between local Borg and NAS; the backup
status verifier also passed. The idle guard was
checked against the running mirror and rejected maintenance with zero host
changes. Its Docker exec return code is explicitly treated as a task failure.

## Baseline archive

The full baseline is in `minecraft-baseline-2026-09-23`, archive ID
`1be998953769da57e1c90ac8fd43e81dd0e19776d91e8cc2669094fa08bb9460`.
The restored full tar matched the original SHA-256:
`152acceea0cd203de5002800016ed50c4f69fa9569c1a92242cb170329fdcb02`.
A complete sky directory was extracted in isolation during that verification.
All three complete server directories were also restored from the archived
recurring tar and passed world, library, version and authentication validation.
The archive creation returned a changed-file warning for its separate recurring
snapshot tar; the full baseline hash comparison passed independently.

## Production deployment

Minecraft deployment on max succeeded after baseline verification. Initial
backend containers remained asleep. An unchanged repeat preserved all container
IDs. A second repeat with sky awake preserved its process start time and left
atm10 and vanilla asleep. Router and proxy are running; only TCP 21212 is
published. Host firewall allows that port. Production status polling reports
sleeping worlds without waking them and rejects unknown hostnames.

Each world was woken separately through a Minecraft login handshake. All three
loaded Minecraft 1.21.1 and their preserved NeoForge versions, reached readiness,
and responded to RCON with zero players. Initial heaps are 1G; limits and maximum
heaps match the runbook. Observed idle container memory was approximately 5 GiB
for sky, 11.7 GiB for atm10, and 4 GiB for vanilla. Gameplay properties, operator
lists, allowlists and ban lists match the baseline. Vanilla logs recipe parsing
errors involving existing mod integrations but reaches readiness; gameplay needs
a matching client check. Snapshot refresh correctly defers while backends run.

## Public port diagnosis

An external TCP check against the old public port 25565 resolved all three names
through public DNS to 135.180.193.156 and reported the port closed. During a repeat
external check, a 20-second packet capture on max's LAN interface saw no packets
for TCP 25565. The router container was listening on that port and UFW allowed
it. This places the observed failure before the host, at the gateway/ISP path.
The public listener was changed to TCP 21212, the previous UFW 25565 rule was
removed, and Cloudflare SRV records now direct all three hostnames to port 21212.
An external TCP check then reported 21212 open. The real outside Minecraft
client test is still pending.

## Follow-up checks

All three servers completed their 900-second idle period, saved every world
dimension and exited with code 0. A subsequent hostname join woke Sky and it
became ready on the second startup. Status polling on port 21212 reports the
sleeping MOTD and leaves ATM10 and Vanilla exited. The production routing fixture passes sleeping/loading MOTDs, status
without wake, unknown-host rejection and selected-backend wake on the pinned
router and socket-proxy images.

The normal Borgmatic run transferred the initial completed snapshot and archived
it under the shared transfer lock. Its NAS replication passed, all 56 archive
names and IDs matched, and the backup status verifier passed.

After all three backends idled, a fresh post-startup snapshot was atomically
published and archived as `nuc-mini-2026-09-23T22:41:56.611254`, ID
`1f4ea49886a93d77f7dc64705ce40148a1346fa6be94b7cfedac9b1b1f1a1f8a`. It
transferred 2.43 GB of changed archive data; NAS replication passed. All 57
archive names and IDs match, the independent snapshot-age check passed, and the
latest snapshot tar was restored into an isolated directory on nuc-mini. All
three restored worlds, installations and authentication settings passed the
validator. The independently verified full baseline remains available.

An external TCP probe reports port 21212 open. The earlier port 25565 probe was
closed and a packet capture on max saw no arriving packets during that check.
The LAN gateway resolver returns 192.168.1.100; the user's Mac normal resolver
still selects public DNS and LAN-to-WAN loopback had refused earlier. The user
plans to test the matching modded clients and an outside connection.

## Pending

Actual LAN and outside Minecraft client logins, including all three matching
modpacks, remain unverified. The user plans to test them now that public TCP
21212 is reachable and the SRV records advertise that port.
