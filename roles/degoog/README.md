# Degoog

Degoog's desired host is `nuc-mini`, at `/opt/docker/degoog`. The existing
installation on `max` must be transferred with the explicit migration below
before ordinary deployment. The role refuses to start an empty replacement.

The public URL remains `https://search.atelier.house`. Traefik reaches the
container through `proxy-network`; TinyAuth continues to allow every PocketID
account. Only the NUC loopback interface publishes port 4444, for provisioning
and the native 4play bridge. There is no LAN backend listener.

## Forward-only migration

This procedure stops Degoog on `max` and causes a brief search outage. It does
not deploy FlareSolverr, configure consumers, upgrade the Degoog image, reset
credentials, change installed extensions, or restart the Firefox/Xorg desktop.

Before the authorized window:

- Update the main checkout and retain the existing encrypted
  `group_vars/degoog/vault.yml`. Required inputs remain
  `vault_degoog_settings_password` and `vault_degoog_4play_password`.
- Verify SSH and privilege escalation for both hosts, available NUC disk space,
  the NUC proxy network, and the existing native 4play bridge.
- Reconcile the changed Komodo declaration before cutover so it no longer
  attempts to deploy Degoog on `max`. Do not run an empty NUC deployment.
- Run static checks and disposable migration tests.

```sh
make check
python3 tests/test_degoog_migration.py
git diff --check
ansible-playbook -i inventory/hosts.yml deploy/degoog_migrate.yml \
  -e degoog_migration_confirm=true
```

The explicit confirmation is required. Check mode is rejected rather than
pretending to simulate a data transfer. Do not use `--limit nuc-mini` as an
isolation boundary: the play intentionally delegates source operations to max.

The playbook verifies destination safety, reserves headroom for staging, and
pulls the unchanged image before stopping the source. It retires
`max:/opt/docker/degoog/compose.yaml` to `compose.retired.yaml` and removes
the source container without removing volumes or data. This also prevents the
boot-time Compose scanner from resurrecting a second instance.

Stopped data is checked for SQLite integrity, archived with restrictive
permissions, transferred through a private temporary controller directory, and
verified by SHA-256 before extraction. Symlinks and special archive entries are
rejected. The destination data directory is installed atomically, with a
checkpoint that distinguishes prepared, restored, and completed transfers.
Re-running the play resumes an incomplete cutover but never replaces restored
data with the old archive. Unexpected destination data causes a refusal.

The destination starts without extension provisioning; routing switches to
Traefik Docker labels and only the native WebSocket bridge is reloaded. The
obsolete source-scoped UFW rule is removed from both hosts. Source data and
root-only transfer archives remain; their deletion is a separate authorized
operation. Controller temporary files are removed even after failure.

There is no automatic rollback or reverse-copy path. On failure, inspect the
failed phase and rerun after correcting it. Do not remove checkpoints or replace
destination data to bypass a refusal. After completion the play only checks readiness.

## Verify the cutover

- NUC `http://127.0.0.1:4444/readyz` returns 200.
- Anonymous public requests redirect to authentication; sign in with a PocketID
  account and verify the search UI and settings password.
- Confirm existing engines, settings, and indexed data are present; run a known
  working engine query and test the 4play connection.
- Confirm Firefox retained its existing profile and the bridge points to
  `127.0.0.1:4444`.
- Confirm no Degoog container remains on max and neither host offers port 4444
  over the LAN. Inspect Komodo's host assignment after resource synchronization.
- Repeat the migration command: it must not copy data or restart the application.

Automated redirect/readiness checks do not establish a successful PocketID login
or browser extension reconnection. Report those checks separately.

## Routine deployment

```sh
make deploy-degoog
```

Extension provisioning can be skipped with `-e degoog_manage_extensions=false`.
The migration always skips it. Changing the transport through normal provisioning
retains its existing settings-password authentication and restart behavior.

FlareSolverr remains a separate standalone service. Its URL is not configured by
this migration. Existing Open WebUI, n8n, Vane, and Kizuna integrations continue
using SearXNG on `max:8889`.

## Maps frontend compatibility

The user-installed `lazerleif/degoog-maps` frontend hard-codes the old `maps`
tab and route names. Apply the guarded compatibility patch with:

```sh
python3 tests/test_degoog_maps.py
ansible-playbook deploy/degoog_maps.yml --check
ansible-playbook deploy/degoog_maps.yml
```

The patch uses Degoog's injected plugin ID for the canonical tab and API path.
It changes only the installed frontend, preserves other code and settings, and
fails on unfamiliar upstream content. Repeat runs make no changes. Reapply after
updating the plugin through the store. No service restart is requested; refresh
the browser without cache after applying and verify the Maps tab renders tiles
and markers. Check mode inspects the installed file but does not modify it.

The separate HERE Places widget requires default coordinates. Its CARTO tile
requests inherit Degoog's `Referrer-Policy: no-referrer`; a CARTO key that requires
a Referer header can therefore reject browser requests even when the key works
in a manual request with that header. This patch does not change tile credentials
or the application's referrer policy.

## Storage and native browser

The NUC backup role includes `/opt/docker`, subject to its exclusions. This
covers deployment files but does not guarantee a consistent live SQLite snapshot.
Stop writers for a controlled copy and verify restored databases before relying
on them; see the [backup runbook](../backup/README.md).

The [native 4play role](../degoog_4play/README.md) remains separately managed and
excluded from routine full deployments. Its Firefox profile, Xorg display
`:1`, and local bridge URL `ws://127.0.0.1:3031/cnc` are preserved.
