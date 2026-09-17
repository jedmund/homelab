# Komodo operations improvements

Status: Resource Sync reconciled and initial operational alerts enabled on
2026-09-17. Alert coverage gaps and remaining workflows are tracked below.
The initial findings below came from read-only MCP calls and
repository inspection. Recheck live state before implementing later changes.

Ansible continues to own Compose, environment, and application configuration
files. Komodo manages operational workflows around those generated files.
See the [Komodo runbook](../komodo/README.md) for current ownership and setup.

## Initial observed state

- Komodo reports two healthy servers, `Atelier` and `Max`, both on version 2.2.0.
- The repository and live installation each contain 58 Stack resources, but
  their membership differs.
- `homelab-stacks` Resource Sync is pending. It targets GitHub's
  `jedmund/homelab` repository, branch `main`, and `komodo/stacks.toml`.
- The sync includes resources and user groups, has deletion disabled, and has
  an empty match-tag filter. The runbook specifies the `homelab` match tag.
- Live resources are missing `beszel-agent-max`, `infra-periphery`, `sglang`,
  and `vllm`. Declarations refer to server `max`; the live name is `Max`.
- Retired names remain: `development`, `media-acquisition`, `media-consumption`,
  and `reading`. Their references and actual use have not been audited.
- Two Procedures exist: `Backup Core Database`, scheduled daily at 01:00,
  and `Global Auto Update`, whose daily schedule is disabled. Both have an
  empty explicit timezone; verify the effective timezone before changing them.
- One Action exists: `kizuna-storybook-review`. No Alerters are configured.
- Komodo marks GitLab and n8n unhealthy. The cause and application impact have
  not been established by this inspection.

## Work queue

### 1. Reconcile Resource Sync

- [x] Inspect the current pending diff and compare resource names, server
      assignments, host paths, tags, and permissions with the repository.
- [x] Resolve the `Max`/`max` naming discrepancy before applying declarations.
- [x] Scope the sync with the intended `homelab` match tag and verify which
      resources and user groups it will affect.
- [x] Add missing resources after checking their generated host files.
      Preserve explicit startup profiles for vLLM and SGLang.
- [x] Confirm replacement coverage and live workflow references before removing retired
      resource entries. Do not delete containers, volumes, or host data as
      part of resource inventory cleanup.
- [x] Apply the reviewed changes and verify the resulting inventory.
- [x] Document the GitLab provider and repository changes needed when the
      repository moves permanently to GitLab.

Done when the intended declarations and live resources agree, the pending diff
is understood, and each resource points to the correct host and deployment path.
See [Resource Sync](https://komo.do/docs/automate/sync-resources).

Reconciliation result (2026-09-17):

- Renamed the Komodo Server resource `Max` to `max`, preserving its ID and
  connection settings.
- Scoped `homelab-stacks` with `match_tags = ["homelab"]`. This filter takes
  tag names, not tag IDs. Kept automatic resource deletion disabled.
- Verified host Compose files, added all four missing Stack resources, and
  corrected AI's run directory from `/opt/stacks/ai` to `/opt/docker/ai`.
- Found no references to the retired entries in live Procedures, Actions, or
  user-group permissions. Their host directories and container projects were
  absent. Detached each entry from its server before deleting it, avoiding
  Komodo 2.2's automatic stack teardown during resource deletion.
- Synced GitHub main at `3da099a`. The resulting 58 resource names exactly match
  the declarations; the final preview has no pending resource, permission,
  variable, or deployment changes and no errors.
- No deployment was requested by the sync. GPU startup profiles were not selected
  or changed. GitLab cutover settings are documented in the Komodo runbook; the
  sync still uses GitHub.

### 2. Establish actionable alerts

- [x] Investigate the GitLab and n8n unhealthy flags and distinguish service
      failures from expected one-shot containers or unsuitable health checks.
- [x] Choose an alert destination and configure an Alerter with scoped rules.
- [x] Route unreachable-host, stack-state, disk-pressure, and supported operation
      failure alerts; document the response and limitations of each category.
- [x] Check overlap with Gatus and Beszel so the same incident does not produce
      redundant notifications.
- [x] Test delivery and recovery notifications using a controlled condition.
- [x] Confirm receipt of the test and stop/recovery messages in Discord.
- [ ] Cover Docker health-check failures while containers remain running.
      Komodo 2.2's Compose state calculation ignores that condition; Gatus does
      not check every container or internal dependency.
- [ ] Route maintenance deployments through a failure-alerting Procedure or
      Action. A failed direct deployment can leave the old stack running and
      produce no state-change alert. This belongs to workstream 3.

Done when a real failure reaches the chosen destination with enough context to
act, and expected transient or completed workloads do not generate noise.
See [Komodo resources](https://komo.do/docs/resources).

Initial implementation (2026-09-17):

- GitLab's active containers were running, its container health check and local
  readiness probe passed, and its sign-in page returned HTTP 200. Its optional
  Renovate cron service was absent. n8n's certificate initializer had exited
  successfully, its sandbox dependencies were healthy, and `/healthz` returned
  HTTP 200. Added only `renovate` and `sandbox-certs` to their respective Komodo
  health exclusions; both stacks now report `running`.
- Created `homelab-operations` using Gatus's existing Discord destination, as
  requested. The webhook is referenced through the secret Komodo variable
  `HOMELAB_DISCORD_WEBHOOK_URL`; its value remains outside tracked files.
- Enabled unreachable-server, disk, stack-state, Build, Repo build, Procedure,
  and Action failure notifications. Existing disk thresholds are 75% warning
  and 95% critical. CPU, memory, image-update, and schedule-start messages are
  excluded from this initial delivery policy.
- Gatus retains HTTP, certificate, and runner checks. Beszel had zero alert
  rules and zero alert-history entries in the live audit. Komodo and Gatus can
  still both report different symptoms of one outage; there is no cross-tool
  deduplication. Core cannot report its own host's complete outage.
- The built-in Discord delivery test succeeded. A disposable, network-isolated
  probe confirmed that a Docker health failure alone produces no stack alert.
  Stopping and restarting the probe produced both state-change alerts, with no
  delivery errors in Core's logs. The probe, its files, and temporary resources
  were removed. GitLab and n8n container start times and restart counts were
  unchanged. The operator confirmed receipt of all three Discord messages.
- Komodo accepted the local declarations in a temporary preview-only Resource
  Sync with no pending resource, permission, variable, or deployment changes.
  The temporary sync was deleted without execution. `make check` passed with
  zero lint failures or warnings.

The live settings are applied. The normal sync reads GitHub `main`; confirm it
contains the operational Alerter and health exclusions before applying a sync.
Older declarations would remove the GitLab and n8n exclusions. Automatic sync
webhooks remain disabled.
See the [alert runbook](../komodo/README.md#operational-alerts) for operation,
credential rotation, monitoring exceptions, and coverage limits.

### 3. Add a maintenance Procedure

- [ ] Choose one low-risk stack as the initial target.
- [ ] Record current image references and verify required backups and inputs.
- [ ] Apply Ansible configuration when needed, then deploy the selected stack.
- [ ] Verify application readiness and the affected behavior after deployment.
- [ ] Stop the workflow on failure and retain the operation's results.
- [ ] Document recovery steps. Do not assume an image rollback can reverse a
      database migration.
- [ ] Define execution permissions before exposing the workflow to CI or agents.

Done when a named-stack maintenance operation is repeatable, produces a useful
execution record, and fails when the application fails to become ready.
Use [Procedures and Actions](https://komo.do/docs/automate/procedures) for staged
execution and application-specific checks.

### 4. Separate update discovery from deployment

- [ ] Evaluate image-update polling for registry-backed stacks without enabling
      automatic deployment.
- [ ] Exclude local-build stacks and account for pinned images and private
      registry authentication.
- [ ] Produce a reviewable list of available updates and affected services.
- [ ] Classify application updates separately from database-engine upgrades.
- [ ] Route approved updates through the maintenance workflow and record the
      deployed image versions.

Done when available updates are visible without changing running services, and
applying an update has a defined validation and recovery procedure.

### 5. Verify backups operationally

- [ ] Check successful execution and freshness of the existing Core database
      backup Procedure, including where its artifacts are retained.
- [ ] Check Borgmatic backup freshness and failure reporting against the
      [backup runbook](../roles/backup/README.md).
- [ ] Add a status workflow that reports missing or stale backups.
- [ ] Define an isolated restore exercise with disposable storage and no writes
      to production databases or volumes.
- [ ] Record the restore result and recovery prerequisites.

Done when backup status reflects usable recent artifacts and a documented
restore exercise has succeeded. A successful scheduled job alone is insufficient.

### 6. Make MCP access durable

The community [Komodo MCP server](https://github.com/MP-Tool/komodo-mcp-server)
version 1.5.0 was installed in a temporary local directory and tested over stdio.
It advertised 88 tools. Initialization and authenticated reads of servers, stacks,
Procedures, Actions, Alerters, and Resource Syncs succeeded against this installation.
Existing vaulted login credentials were supplied in process environment variables.
The initial connection test performed no resource mutations, and its processes
were stopped. The later Resource Sync reconciliation is recorded above.
This is not yet a persistent agent connection or a full compatibility test.

- [ ] Create a dedicated read-only Komodo identity for routine agent inspection.
- [ ] Pin the MCP package version and keep credentials outside tracked files.
- [ ] Configure a local stdio connection in the intended agent client.
- [ ] Verify that the identity cannot mutate resources; tool descriptions alone
      do not enforce authorization.
- [ ] Confirm secret redaction for the read tools that will be used, especially
      logs and resource configuration.
- [ ] Document installation, credential rotation, startup, and removal.
- [ ] Consider operational access only for explicitly approved maintenance
      workflows, with separate credentials and permissions.

Done when an agent can inspect the homelab through a reproducible connection
with enforced read-only access and documented credential handling.

## Suggested order

Reconcile Resource Sync, establish alerts, and implement one maintenance
Procedure first. Add update reporting and backup verification around that
workflow. Persistent read-only MCP access can be prepared alongside the inventory
audit; write access should follow the operational permission design.

Track implementations through linked PRs and replace checklist items with dated
validation results as work completes. Updating this document does not authorize
resource changes, alert delivery, or deployments.
