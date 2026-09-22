# FlareSolverr

Standalone challenge-solving API on `nuc-mini`, managed at
`/opt/docker/flaresolverr`. The official v3.5.2 image is pinned by digest and
includes its own browser. No host desktop, GPU access, or credentials are required.
This deployment does not configure Degoog, Prowlarr, or any other consumer.

## Access

| Caller | Base URL |
| --- | --- |
| NUC host | `http://127.0.0.1:8191` |
| NUC containers attached to `shared-network` | `http://flaresolverr:8191` |
| `max` | `http://192.168.1.6:8191` |

API commands are POST requests to `/v1`; `/health` is a lightweight GET.
There is no public DNS record, Traefik route, or interactive authentication.
The API trusts its callers and can fetch arbitrary URLs. Do not expose it to
untrusted workloads. Other LAN hosts must use an SSH tunnel, for example
`ssh -L 18191:127.0.0.1:8191 nuc`, then `http://127.0.0.1:18191`.

The role owns only the `inet homelab_flaresolverr` nftables table. Its forward
hook filters Docker-published traffic by original destination; UFW alone does
not protect published Docker ports. Same-host shared-network callers are trusted.
Bindings are IPv4-only and inventory-derived. The default remote allowlist is
`max` alone. Changes replace this table atomically, without flushing other rules.

A Docker unit drop-in requires the restriction to load at boot. A malformed
firewall configuration therefore prevents Docker startup rather than exposing
the API. Installing the drop-in does not restart Docker. Stopping the firewall
unit does not remove its rules. Do not restart Docker just to test this on the
production NUC; use an isolated fixture or a separately scheduled maintenance window.

## Deploy and validate

```sh
make check
python3 tests/test_flaresolverr.py
git diff --check
make -C deploy check STACK=flaresolverr
make -C deploy flaresolverr
```

The Python tests require the Ansible environment's PyYAML and Jinja2. Run the
deployment a second time and confirm no container recreation. Komodo's stack
uses the existing `Atelier` server; automatic updates are disabled. Docker health
and Komodo provide initial monitoring. No Gatus networking is changed.

Verify local `/health`, then the LAN endpoint from `max`, and confirm a client
outside the allowlist cannot connect. Test real browser execution separately:

```sh
ssh nuc 'curl -fsS --max-time 90 http://127.0.0.1:8191/v1 \
  -H "Content-Type: application/json" \
  -d '\''{"cmd":"request.get","url":"https://example.com","maxTimeout":60000}'\''' \
  | python3 -c 'import json,sys; x=json.load(sys.stdin); print(x["status"], x.get("solution", {}).get("status"))'
```

Expect `ok 200`. Do not log returned cookies or HTML. Also create and destroy a
uniquely named test session using `sessions.create` and `sessions.destroy`.
An ordinary-page test establishes browser execution, not universal challenge support.

## Storage and resources

Sessions are memory-owned and disposable; `/config` is temporary storage.
There is no session backup or dedicated vault. Generated Compose configuration
is rebuildable and covered by the NUC's existing file-level backup policy.
The default limits are two CPUs, 2 GiB memory and 512 MiB shared memory. Increase
them deliberately if approved concurrency requires it. Consumers must destroy
sessions they no longer need; resource limits are not a request queue.

Logs rotate using shared settings. `warning` avoids upstream INFO request-body
logging; error messages may still include requested URLs. `LOG_HTML` stays off.
Use short-lived controlled diagnostics rather than persistent debug logging.

## Removal

Remove the Compose service before removing its firewall restriction. Then remove
the Docker drop-in, reload systemd, disable the firewall unit and remove only
its dedicated nftables table. Do not flush the host ruleset. Removal is a separate
authorized operation, not part of routine reconciliation.
