# Host log collectors

Vector sends logs to the [retained logging backend](../logging/README.md).
Deploy the backend before enrolling a collector. Inventory group `vector`
includes the Linux servers, gaming PC, Dokploy guest, and native macOS host.
Hosts that are offline remain configured but unverified.

Linux collectors run in the `vector` Compose project at `/opt/docker/vector`.
They read the Docker API, host journal, and selected application files. Docker
socket access is privileged even with a read-only socket mount. Keep the agent
trusted and its API and metrics listeners bound to loopback. No application's
Docker logging driver is changed. The container uses the Debian image because
the journal source requires `journalctl`.

The macOS collector runs as `house.atelier.vector` in the login user's
LaunchAgent domain. The archive is pinned by version and SHA-256. State and
credentials live under `~/.local/share/homelab-vector`. Collection includes
`~/Library/Logs/*.log`, Netdata logs, and readable system logs. Apple's Unified
Log is not collected by this user agent. Allow the native `vector` binary in
**System Settings → Privacy & Security → Local Network**, then verify delivery.

Each collector reuses its distinct client certificate from the backend.
Private keys are transferred under `no_log` into `0600` files. Both the server
and client certificate are validated. An arbitrary LAN client cannot ingest
or query logs.

The Loki sink has a persistent 10 GiB disk buffer. At capacity it blocks
upstream ingestion. It retries recoverable destination errors and synchronizes
data to disk every 500 ms. Events not yet synchronized, rejected events,
source rotation before collection, exhausted disk space, and outages exceeding
available buffer capacity can still lose logs. This buffer is separate from
the NAS archive's 90-day retention. Keep the data directory and sink name when
upgrading. Delivery can produce duplicates after recovery. Repeat the
outage-and-restart test before upgrades.

Source timestamps older than 167 hours are filtered before batching, below
Loki's 168-hour ingestion cutoff. This backfill window prevents expired history
from invalidating current entries in the same request. The journal begins at
enrollment; file history can be backfilled. Full prompts
and request bodies are not deliberately captured. Common Authorization values
are redacted, but applications may still emit other sensitive information.

Docker and journal entries preserve their source timestamps. Traefik JSON file entries
use their `StartUTC`; other file entries use collection time; consult timestamps inside the line when examining backfilled
files. Local replay state is excluded from Borg; configuration and TLS keys
remain covered. The NAS archive is the retained log store.

Every host emits a minute heartbeat. Linux uses a systemd timer and journal
message; macOS uses a LaunchAgent and a file. The backend queries those source
labels end to end. Process readiness alone is not proof of delivery.

On the NUC, Traefik's file log is checked for rotation every fifteen minutes,
with a 100 MiB size threshold and seven rotations. Rotation signals Traefik to
reopen the file and does not restart the proxy or Docker.

```sh
make -C deploy deploy STACK=vector EXTRA_ARGS='--limit max'
ssh max 'curl -fsS http://127.0.0.1:18686/health'
ssh max 'curl -fsS http://127.0.0.1:19598/metrics'
ssh mac 'launchctl print gui/$(id -u)/house.atelier.vector'
python3 tests/test_logging_live.py
```

Add explicit `vector_extra_files` paths and read-only mounts for applications
that log only to files. Paths must match the collector's view of the filesystem.
Never archive vaults, environment files, databases, or application data trees.

For hosts enrolled during rollout, stop the earlier Alloy collector only after
Vector has delivered a new event. Preserve `/opt/docker/alloy` and the macOS
`~/.local/share/homelab-alloy` directory while examining any unsent history.
Remove its Komodo resource and unload its LaunchAgent; do not erase its state
as part of routine deployment.
