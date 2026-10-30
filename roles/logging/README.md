# Homelab logs and metrics

The `logging` stack on `nuc-mini` owns Loki, Grafana, a dedicated Garage
object store, the certificate-authenticated ingestion gateway, and collection
health checks. Prometheus stores time series, and Unpoller collects read-only
UniFi Network statistics from the UDM Pro. [Vector](../vector/README.md) collects container output, Linux
journals, and configured application log files. Logs remain available after
the source container is removed or recreated.

## Access and storage

The administrative UI is `https://logs.atelier.house`. Grafana authenticates
directly with PocketID through OIDC, using PKCE and signed ID-token validation.
The PocketID client and Grafana both require the `sysadmins` group, whose
initial member is the primary administrator. Group members receive the Grafana
organization Admin role. Anonymous access, basic login, and forwarded-user
authentication are disabled. The route has no TinyAuth middleware.

The existing administrator account was retained by linking its authentication
record to the verified PocketID subject. A consistent database snapshot from
before that change is retained at `backup/pre-oidc-grafana.db`. If restoring
that earlier snapshot, its account still has the former proxy authentication
record; link the verified PocketID subject again before testing native login.

Loki's unauthenticated API is isolated on the stack's internal network and
on `127.0.0.1:13100` for host administration. The LAN listener at
`192.168.1.6:13443` accepts only log pushes authenticated with a collector
client certificate. It does not expose queries or delete operations.

Log retention is 90 days (`2160h`), applied by Loki's compactor. Deletion is
asynchronous and has an additional two-hour delay. Retention is not a storage
quota. Monitor NAS usage and ingestion volume before changing the limit.

| Data | Location | Recovery requirement |
| --- | --- | --- |
| Compressed chunks and uploaded indexes | NAS Homelab share, `Logs/garage` | Preserve these objects and Garage metadata together |
| Garage metadata and automatic snapshots | `/opt/docker/logging/garage-meta` | Local SSD; consistent snapshots included in Borg |
| Loki write-ahead log, active index, compactor markers and caches | `/opt/docker/logging/loki-state` | Persistent local SSD; never put the WAL on NFS |
| Prometheus time series | `/opt/docker/logging/prometheus-data` | Local SSD; consistent daily TSDB snapshot under `backup/prometheus/` |
| Grafana state | `/opt/docker/logging/grafana-data` | Consistent daily SQLite backup under `backup/` |
| CA, server and collector identities | `/opt/docker/logging/tls` | Private keys are persistent and covered by encrypted Borg backups |

The role mounts a dedicated NFS path and verifies its filesystem type before
creating data directories. Garage's bind mount disallows automatic path
creation. A missing NAS mount must not redirect log data onto the NUC root
filesystem. The NAS share remains a single storage failure domain; this is
not an immutable or geographically separate audit archive.

## Dashboards and metrics

Grafana opens the managed **Homelab log browser** by default. The **Homelab**
folder also contains **Web traffic and performance**, **AI workload
performance**, **UniFi network health**, **Host health and capacity**, and
**Storage and backup health**. Dashboards are provisioned from this role; edit their JSON
source rather than making UI changes that provisioning will overwrite.

The web dashboard parses Traefik JSON access records, including successful
requests. Its domain field accepts a regular expression. Duration includes
streaming responses; response-body bytes are not total network traffic.
Vector uses Traefik `StartUTC` for newly collected records. Older backfilled
file records used collection time. Historical error-only access records do
not establish request totals before full access logging began.

Prometheus scrapes Loki, llama-swap, vLLM, GPU metrics from the existing
Netdata parent, and Unpoller. The AI dashboard shows all three physical GPU
indices from Netdata. Per-model token counts, queue depth, and latency
histograms currently cover the vLLM-served GLM model; llama-swap access logs
provide separate request and latency panels. These metrics do not reconstruct
history from before enrollment or token counts for other inference servers.

Metrics remain on the NUC SSD for up to 90 days or 20 GB of retained blocks,
whichever limit expires first. WAL, current head, and backup snapshots consume
additional disk space. Prometheus is accessible only on its Docker networks
and NUC loopback `127.0.0.1:19090`; Grafana queries it internally. Its admin
API is enabled for snapshots and has no public or LAN listener.

UniFi collection uses the existing `unifimcp` account with read-only Network
permissions and `vault_unifi_password` in the encrypted
`group_vars/agents_linux/vault.yml`. The NUC already belongs to that group.
No new administrator or persistent key is created. Unpoller resolves
`unifi.local` to `192.168.1.1` and verifies the controller hostname against
`files/unifi-controller.crt`. When the controller certificate changes, verify
its fingerprint through a trusted path, replace the pinned public certificate,
and redeploy. Do not disable TLS verification to repair collection. UniFi
metrics are available in **Homelab metrics** and the network dashboard.
WAN counters describe Internet traffic; client counters can also include LAN
traffic. Client retry rates are event rates, not retry percentages.

The host dashboard scrapes normalized Netdata interval averages through the
existing parent for `nuc-mini`, `max`, and `mac-mini`. Negative I/O directions
are displayed as positive rates. RAM categories differ by operating system;
shared APFS pools and layered block devices must not be summed.

UNAS collection is enabled with `logging_unas_enabled` after local monitoring
accounts are configured on both consoles. Store the shared credentials as
`vault_logging_unas_username` and `vault_logging_unas_password` in the logging
vault. The pinned Unpoller input supports username/password sessions. Each
NAS has an isolated collector because its certificate identifies the same
`unifi.local` hostname. Each container resolves that hostname to its assigned
NAS and verifies the matching pinned public certificate, `unas-files.crt` or
`unas-games.crt`. No collector has a published port or an agent on the NAS.

Storage panels show pool usage and RAID redundancy, physical disk health,
temperatures, SSD cache utilization/hit rate/endurance, rebuild progress, and
short-term growth forecasts. Forecasts require at least 60 samples; a NAS
without SSD cache has no cache metrics. Missing NAS metrics are unknown,
not healthy. Health checks require pool-capacity telemetry from each configured
console, in addition to healthy scrape endpoints. UniFi Drive cloud-backup job
success and snapshot age are not collected.

The backup role publishes cached verification metrics every five minutes. The
logging checks service exposes those files privately to Prometheus; it has no
Docker socket and does not execute backup commands during HTTP requests. The
dashboard reports collection age, repository contention, last observed local Borg
archive age, complete verification and mirror freshness, and the last recorded Prowlarr restore proof.
Previously verified timestamps remain visible during collection failures;
check their age. Restore proof covers that SQLite dump only.

## Inputs and deployment

The encrypted `group_vars/logging/vault.yml` requires:

- `vault_logging_admin_password`: Grafana's persistent recovery password;
- `vault_logging_garage_rpc_secret`: 64 hexadecimal characters;
- `vault_logging_s3_access_key`: Garage key ID (`GK` plus 24 hex characters);
- `vault_logging_s3_secret_key`: persistent S3 secret.
- `vault_logging_oidc_client_id`: confidential PocketID client ID;
- `vault_logging_oidc_client_secret`: persistent PocketID client secret.

Create the `Grafana` PocketID client with callback
`https://logs.atelier.house/login/generic_oauth`, PKCE required, and group
restriction enabled. Allow only `sysadmins` and enroll the intended
administrator in that group. Its name must match `logging_oidc_allowed_group`.
Store the generated client credentials in the logging vault. Preserve existing
credentials and Grafana data on redeployment.

Generate these once for a new installation. Preserve them on redeployment.
The role generates its CA and TLS private keys once on the logging host;
do not delete them to repair a failed deployment. Certificates currently last
825 days, and the CA lasts ten years. Schedule certificate renewal before
expiry and distribute renewed identities to every enrolled collector.

Deploy in this order:

```sh
make check
python3 tests/test_logging.py
python3 tests/test_logging.py --validate-configs
git diff --check
make -C deploy logging
make -C deploy deploy STACK=vector EXTRA_ARGS='--limit max'
make -C deploy deploy STACK=vector EXTRA_ARGS='--limit nuc-mini,mac-mini'
```

Register the PocketID client and its group before exposing Grafana
to browsers. Create the `logs.atelier.house` DNS record and include it in
ddclient. Deploy Gatus only after the expected collector set is sending
heartbeats. Image references are pinned; upgrades require release-note and
configuration checks before deployment.

Komodo declarations manage `logging`, `vector-nuc`, and `vector-max` from the
Ansible-rendered host files, with automatic updates disabled. Refresh and
review Resource Sync before applying these additions. A native macOS
collector is a LaunchAgent, not a Komodo Compose stack. Offline collectors
can be configured in inventory but must not be reported as deployed.

## Verification

On the NUC:

```sh
curl -fsS http://127.0.0.1:13100/ready
curl -fsS http://127.0.0.1:19090/-/ready
curl -fsS http://127.0.0.1:19090/api/v1/targets
docker compose -f /opt/docker/logging/compose.yaml ps
docker exec logging-checks python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health').read().decode())"
```

Gatus checks recent heartbeats from `logging_expected_hosts`, NAS NFS
reachability and capacity, metadata snapshot freshness, and Prometheus scrape
target health. A missing host
heartbeat is a failure even if its collector process is still running.
Add a host to the expected set only after its collector is enrolled. The
gaming PC can be intentionally offline; do not require a continuous heartbeat
from it unless that operating policy changes.

In Grafana Explore, select **Homelab logs** and query, for example:

```logql
{host="max", job="docker", container="llama-swap"}
{host="nuc-mini", job="files"} |= "traefik"
{host="max"} |= "homelab-log-heartbeat"
```

Use the filename label to distinguish application file logs. Container IDs,
IPs, request IDs, and full URLs are not indexed as Loki labels. Queries inspect
the log contents for these values.

Prove durability with uniquely named disposable canary containers. Query
their markers after container deletion/recreation, collector restart, and
Loki restart. Stop or pause only the dedicated logging destination when
testing buffering; do not interrupt the shared NAS or restart Docker. Verify
that a marker emitted during an ingestion outage arrives after recovery.
Force a Loki flush and query through storage after restart to establish NAS
object-store persistence. Use disposable fixtures to test accelerated
retention; never shorten production retention to test deletion.

Run `python3 tests/test_logging_live.py` for the disposable-container checks.
It stops the logging gateway, removes the source during the outage, restarts
the collector, restores ingestion, and restarts Loki. Do not deploy the
backend concurrently with this test.

NAS index uploads are asynchronous. Loki rotates the active TSDB index head
on a fifteen-minute cycle, so a fresh store-only query can lag normal queries
until the index is uploaded. Normal queries also read recent local ingester
state. Preserve that state across container recreation.

Repeat deployment and compare container IDs. An unchanged run must not
recreate the logging backend or collectors.

## Content and coverage

Collectors preserve emitted logs, not arbitrary application state. Docker
stdout/stderr are discovered automatically; file-only application logs need
explicit paths. The NUC includes GitLab's log tree and Traefik's access log.
Linux journals cover host services, SSH, and firewall messages. macOS
collection covers configured service files and readable system logs; Apple
Unified Logging is not collected by a user LaunchAgent.

llama-swap emits proxy, HTTP, and upstream logs to stdout. Traefik records
successful and unsuccessful access requests in JSON, drops query parameters,
and drops request headers. This does not enable request-body logging or
archive llama-swap's in-memory captures. Existing application logs can contain
prompts and other user content. A collector redaction
stage removes common Authorization credential values; it is not a guarantee
that every application log is free of secrets. Keep the NAS data private.

The snapshot job creates a consistent Grafana SQLite copy and requests a
Garage metadata snapshot daily before the existing Borg job. It also requests
a Prometheus TSDB snapshot, including the current head, and atomically publishes
its immutable blocks under `backup/prometheus/`. A file lock serializes cron
and deployment snapshots. Hard links keep one additional snapshot view without
copying unchanged blocks; retained backup blocks can outlive active retention.
The high-volume Loki working directory, live Prometheus data directory, and
live application databases are excluded from Borg.
NAS objects need the NAS's separate protection and snapshot policy. Restore
Garage metadata matching its object blocks before starting Loki against a
recovered store; restore Grafana from `backup/grafana.db` with Grafana stopped.
To restore metrics, stop Prometheus, preserve its existing data directory, copy
`backup/prometheus/` into an empty `prometheus-data/` directory with UID/GID
65534, then start Prometheus and query a metric from the snapshot time range.
Do not merge snapshot blocks into a running TSDB or delete the previous data
until recovery is verified.

## Removal

Stop collectors before retiring ingestion. Preserve NAS objects, Garage
metadata, Grafana backups, certificates, and vaults for the remaining
retention window. Removing a role does not erase those data. Remove the UI
route, PocketID client registration, DNS, Gatus check, and Komodo declarations as a
separate reviewed operation. Never use `docker compose down -v` to perform
routine maintenance.
