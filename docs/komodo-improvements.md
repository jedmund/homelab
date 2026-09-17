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

Purpose: make an approved update repeatable and observable. Today an operator
must remember backup checks, the deployed version, deployment commands, and
post-deployment checks. A Procedure records those steps in one execution and
stops when a prerequisite or readiness check fails. Its failure alert also
covers an update that fails while the old containers remain running.

The initial workflow should accept one named stack and an approved image
revision. Check required backup freshness, record current image references,
apply Ansible configuration if needed, deploy, and verify application readiness.
Start with manual execution for one low-risk service. Keep automatic updates
disabled; extending the workflow to other services requires their own health
checks and recovery prerequisites. A successful container start alone is not
a successful maintenance operation.

- [x] Choose one low-risk stack as the initial target.
- [x] Pin BentoPDF `2.8.8`, add Docker health, and enforce its zero-mount backup
      exemption in the preflight.
- [x] Add allowlisted Ansible staging and a fixed, sequential, failure-alerting
      Komodo Procedure.
- [ ] Deploy the health-check bootstrap, prove staging preserves container
      identity, reconcile the resources, and rehearse at the existing digest.
- [x] Stop the workflow on failure and retain the operation's results.
- [x] Document recovery steps. Do not assume an image rollback can reverse a
      database migration.
- [x] Keep execution admin-only; expose nothing to CI, agents, or MCP.

Done when a named-stack maintenance operation is repeatable, produces a useful
execution record, and fails when the application fails to become ready.
Use [Procedures and Actions](https://komo.do/docs/automate/procedures) for staged
execution and application-specific checks.

Repository implementation (2026-09-17): BentoPDF `2.8.8` is pinned to OCI index
digest `sha256:3d62b8f8eece5fe947026ac3925ff08fda245b3d6ba2c3916b94da91e0010c74`.
`make -C deploy stage STACK=bentopdf` renders its Compose and maintenance check
without running Compose. `maintain-bentopdf` runs preflight, `DeployStack`, and
post-deployment health/digest verification in separate stages. This repository
work was not deployed; no container identities or Komodo execution URLs exist
yet. The first real image upgrade remains the replacement test.

### 4. Separate update discovery from deployment

Benefit: one reviewable update list replaces repeated registry and dashboard
checks. Discovery does not change running services; approved updates use the
maintenance Procedure. Database upgrades remain separate decisions.

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

Benefit: establish that recent backup artifacts exist and can be restored before
depending on them for maintenance. A green scheduled job is not proof that its
output is usable. Restore exercises use isolated storage, never production data.

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

### 7. Reduce validation time and cost

GitHub runs the fast, host-independent checks for pull requests. It does not run
validation on pushes to `main`; full GitHub validation remains an explicit manual
dispatch because it consumes Actions minutes. GitLab selects static and lifecycle
jobs from the change set and retains scheduled and explicit full validation.

The successful [PR #261 validation run](https://github.com/jedmund/homelab/actions/runs/35198849488)
took about 12 minutes for documentation changes. Its timestamps give this
baseline:

| Phase | Approximate duration | Cause |
| --- | --- | --- |
| Validation image build | 1 minute | Tool and collection installation on a fresh runner |
| Playbook syntax | 37 seconds | Each standalone playbook launches Ansible serially |
| Lint | 79 seconds | Whole-repository Ansible lint |
| Lifecycle suite | 9 minutes | Nine role fixtures run serially, including repeated build and deployment scenarios |

The subsequent [PR #262 run](https://github.com/jedmund/homelab/actions/runs/35203408930)
took about 18 minutes: image setup about 68 seconds, syntax 54 seconds, lint
137 seconds, and lifecycle checks about 14 minutes. Both runs passed. The
variation affected several phases; the serial lifecycle suite dominated both.

Change selection has the largest potential saving in billed minutes. Parallel
jobs reduce elapsed time but may increase billed minutes through repeated setup.
Cache work should follow the measured bottlenecks rather than assuming the
image build dominates.

- [x] Replace the temporary GitHub pause with automatic fast pull-request checks,
      no `main` push trigger, and manual fast or full dispatch.
- [x] Add shared change classification for GitHub and GitLab, using the actual
      review base. Cover renames, missing history, and shared inputs; unknown
      changes must select full validation rather than silently skip it.
- [x] Give documentation-only changes local-link, path, and diff checks without
      building the Docker validation image.
- [x] Validate Komodo declarations with TOML parsing and structural checks
      without running unrelated Compose lifecycle fixtures or contacting hosts.
- [x] Run static Ansible checks for configuration changes and select affected
      role fixtures. Shared lifecycle code, tooling, inventory, or test changes
      require the broader suite. Preserve all existing behavioral scenarios.
- [x] Run full lifecycle fixtures in four fixed parallel jobs, with isolated
      Docker daemons, temporary roots, and retained per-role failure logs. Set
      each job to three CPUs and 6 GiB; revise these limits from runner timing
      and contention data.
- [ ] Cache or publish a pinned validation tool image, rebuilding it when the
      Dockerfile or pinned requirements change. Use a cache usable on the
      destination platform; keep credentials out of layers and artifacts. The
      current launcher reuses the runner's Docker layer cache but does not share
      it with fresh GitHub runners.
- [x] Remove duplicate static checks and report phase and fixture timings as
      separate CI steps. Keep an always-running aggregate result so conditional
      jobs cannot strand required checks.
- [x] Retain full scheduled and explicit validation on GitLab.
- [x] Cover change selection, rename parsing, safe fallback, Markdown links, and
      Komodo structure with regression tests.
- [ ] Measure representative CI runs, including elapsed time and billed GitHub
      runner minutes before expanding automatic GitHub checks.
      Targets are under one minute for documentation/declaration changes and
      three to five minutes for full validation; these are targets, not results.

Local warm-cache validation on 2026-09-17 completed the fast phase in 0.03
seconds and the static job in 63 seconds. Four concurrent lifecycle jobs took
80, 85, 96, and 101 seconds, including their cached one-second image builds.
All nine role fixtures passed. These figures confirm the split and resource
isolation locally; GitLab runner timings and GitHub billed minutes remain to be
measured after publication.

The first automatic [GitHub pull-request run](https://github.com/jedmund/homelab/actions/runs/35209700326)
on 2026-09-17 passed the fast job in five seconds; the full job remained skipped.
GitLab full-matrix timing and account-level GitHub billing data remain outstanding.

Done when routine changes run the relevant gates, full validation remains
available, and measured runtime and cost justify the chosen automatic triggers.
This work changes repository validation, not homelab deployment behavior.

## Suggested order

Address validation runtime and cost next. Resource reconciliation and initial
alerts are already applied. Then implement one manually executed maintenance
Procedure with backup preconditions, followed by update reporting and restore
verification. Persistent read-only MCP access can be prepared independently;
write access should follow the operational permission design.

Track implementations through linked PRs and replace checklist items with dated
validation results as work completes. Updating this document does not authorize
resource changes, alert delivery, or deployments.
