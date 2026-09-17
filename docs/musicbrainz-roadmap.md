# MusicBrainz recovery and maintenance roadmap

Status: production recovery is planned but not deployed. Replication monitoring
is being prepared in GitHub PR #212. Recheck live state before every phase;
the observations below are a dated incident record, not current host evidence.

The [MusicBrainz runbook](../roles/musicbrainz/README.md) owns operating
commands and verification. This document tracks the staged recovery and the
work needed to prevent another silent stale mirror.

## Observed state on 2026-09-17

- Production ran `v-2026-04-27.0`, PostgreSQL 16.3, and schema sequence 30.
- The database stopped at replication sequence 185879 on 2026-05-11. Upstream
  served sequence 189072 under schema 31 at the time of inspection.
- The scheduled 2026-08-19 upgrade stopped before making changes because root
  could not use the deployment user's Git checkout. Its generic recreate script
  also omitted upstream's required PostgreSQL, collation, and SIR transitions.
- A later deployment restored the old pinned checkout and upstream's unmonitored
  cron. The API remained available but served data about 129 days old.
- The database and search volumes used about 57 GB and 84 GB respectively;
  the host had about 411 GB free.

## Work queue

### 1. Restore replication visibility

- [ ] Rebase and merge PR #212 without changing the upstream release pin.
- [ ] Create a dedicated Healthchecks.io check for `0 3 * * *` UTC with six
      hours of grace, and store its ping URL in the MusicBrainz vault.
- [ ] Deploy the role in an authorized window and confirm the wrapper reports
      the existing schema mismatch as a failure despite upstream exiting zero.
- [ ] Confirm the alert is received, container logs contain the wrapper verdict,
      and a second Ansible run does not rebuild unchanged images.

Done when failed, stale, and missing replication runs are externally visible
while the schema-30 stack remains pinned and usable.

### 2. Prepare the schema-31 migration

- [ ] Create a dependent PR with the release-specific procedure and final pin.
      Use `v-2026-05-13.0-mbdb31-pg18` for the corrected migration step, then
      advance to the reviewed current release (`v-2026-07-30.1` as observed).
- [ ] Re-read both release notes immediately before maintenance and update the
      procedure if the target or prerequisites changed.
- [ ] Put MusicBrainz deployments under a maintenance freeze from the first
      host checkout change until the final version pin is merged and deployed.
- [ ] Record current checkout, image IDs, schema, PostgreSQL version,
      replication control row, service state, volume sizes, and free space.
- [ ] Stop the stack and clone `musicbrainz_pgdata` and
      `musicbrainz_solrdata` to dated rollback volumes. Verify both copies before
      restarting any writer.

Done when the migration PR has passed validation, the maintenance window and
rollback trigger are explicit, and verified rollback volumes exist.

### 3. Upgrade PostgreSQL and the MusicBrainz schema

- [ ] Disable replication without running `admin/configure`, which would
      overwrite the Ansible-managed `COMPOSE_FILE` setting.
- [ ] On the last schema-30 release, remove the old SIR/AMQP triggers as required
      by upstream.
- [ ] Check out the corrected schema-change release and render a temporary
      cron-free Compose configuration from the same source overlays as the role.
- [ ] Run upstream's PostgreSQL 16 to 18 upgrader and verify the server reports
      PostgreSQL 18 before proceeding.
- [ ] Rebuild collation-dependent indexes, run `upgrade-db-schema.sh`, verify
      schema sequence 31, install the new SIR schema, and apply exactly the first
      schema-31 replication packet.
- [ ] Stop and restore the dated database and search volumes if any required
      checkpoint fails. Restore the old checkout and rendered configuration
      before bringing schema-30 services back up.

Done when the corrected intermediate release runs PostgreSQL 18 and schema 31,
and accepts the first schema-31 packet.

### 4. Catch up and return configuration to Ansible

- [ ] Advance to the reviewed current upstream release and deploy the dependent
      version-pin PR so the host and repository agree.
- [ ] Run monitored replication on demand until no packet is pending. Confirm
      the last replication age is below 36 hours and compare the local sequence
      with the newest authenticated upstream packet.
- [ ] Confirm the expected schema-31 services are running, obsolete RabbitMQ and
      Redis containers are absent, and `sir.pending_data` drains.
- [ ] Verify WS/2 search locally and from Multi-Scrobbler and Album Sort.
- [ ] Resume the Healthchecks schedule, confirm a successful ping, and repeat
      the Ansible deployment to establish idempotence.
- [ ] Retain rollback volumes for seven days. Remove them only after the soak
      period and explicit approval.

Done when data freshness, search indexing, downstream consumers, monitoring,
and repository-to-host version agreement all pass.

### 5. Keep the mirror current

- [ ] Treat replication age, not container uptime or upstream's exit code, as
      the data-freshness signal. Investigate every 36-hour breach.
- [ ] Review every pinned-release change and keep schema/database upgrades out
      of routine image updates. Recent schema releases landed in May, but that
      timing is not guaranteed.
- [ ] For each future schema release, create a release-specific migration plan,
      verified rollback copies, a maintenance freeze, and the same post-upgrade
      acceptance checks. Do not revive a generic annual upgrade script.
- [ ] Add MusicBrainz release discovery and approved deployment orchestration to
      the separate [Komodo maintenance work](komodo-improvements.md#4-separate-update-discovery-from-deployment).
      Discovery must not automatically deploy database or schema changes.

Done when replication failures page independently of the host, upstream releases
enter a review queue, and every schema change has an explicit migration and
rollback plan before its version pin moves.
