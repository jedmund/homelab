# Retained homelab logs

The `logging` stack on `nuc-mini` owns Loki, Grafana, a dedicated Garage
object store, the certificate-authenticated ingestion gateway, and collection
health checks. [Vector](../vector/README.md) collects container output, Linux
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
| Grafana state | `/opt/docker/logging/grafana-data` | Consistent daily SQLite backup under `backup/` |
| CA, server and collector identities | `/opt/docker/logging/tls` | Private keys are persistent and covered by encrypted Borg backups |

The role mounts a dedicated NFS path and verifies its filesystem type before
creating data directories. Garage's bind mount disallows automatic path
creation. A missing NAS mount must not redirect log data onto the NUC root
filesystem. The NAS share remains a single storage failure domain; this is
not an immutable or geographically separate audit archive.

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
docker compose -f /opt/docker/logging/compose.yaml ps
docker exec logging-checks python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health').read().decode())"
```

Gatus checks recent heartbeats from `logging_expected_hosts`, NAS NFS
reachability and capacity, and metadata snapshot freshness. A missing host
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
Garage metadata snapshot daily before the existing Borg job. The high-volume
Loki working directory and live application databases are excluded from Borg.
NAS objects need the NAS's separate protection and snapshot policy. Restore
Garage metadata matching its object blocks before starting Loki against a
recovered store; restore Grafana from `backup/grafana.db` with Grafana stopped.
## Removal

Stop collectors before retiring ingestion. Preserve NAS objects, Garage
metadata, Grafana backups, certificates, and vaults for the remaining
retention window. Removing a role does not erase those data. Remove the UI
route, PocketID client registration, DNS, Gatus check, and Komodo declarations as a
separate reviewed operation. Never use `docker compose down -v` to perform
routine maintenance.
