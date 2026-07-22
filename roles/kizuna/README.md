# Kizuna production runbook

The public deployment probes in the API and app pipelines verify that Komodo
finished successfully, the exact commit is live, the SPA deep-link fallback
works, API credentialed CORS is correct, and the private Garage endpoint accepts
the expected upload preflight. The checks below cover the authenticated and
stateful behavior that should not be automated with production credentials.

## First acceptance pass

1. Deploy this role and the backup role, then merge one API or app change so its
   default-branch pipeline exercises the Komodo completion and revision gates.
2. Confirm `docker compose ps` reports the API, Postgres, Redis, and
   screenshotter as healthy. Confirm the worker is running.
3. Sign in through PocketID. Sign out and back in with the password path as a
   second check when password login is enabled.
4. Create and edit a two-line note, reload it, and confirm autosave preserved
   the content. Turn a note into a task; exercise date, time, and priority.
5. Capture a generic link and an image. Confirm the link preview completes, the
   image survives a reload, and removing a parsed embed prevents its node from
   being created.
6. Start a chat that uses a source. Confirm streaming, cancel/reload behavior,
   the collapsible Thinking section, and the inline Sources pill. Open Run
   details from the overflow menu.
7. Create and remove a connection between two nodes and verify both node detail
   views agree.
8. Repeat the capture/edit/task path once from a narrow mobile viewport.

Record friction as product issues; do not broaden this rollout PR with fixes
found during the pass.

## Reaper audit

`KIZUNA_REAPER_DRY_RUN` intentionally starts at `1`. Run the job once after the
stack has accumulated representative uploads:

```sh
docker exec kizuna-worker bin/rails runner 'PruneUnclaimedUploadsJob.perform_now' 2>&1
docker logs --since 24h kizuna-worker 2>&1 | grep '\[reaper\]'
```

For every `DRY_RUN_WOULD_DELETE` line, verify the ledger row is unclaimed and
older than the grace period, and that its object key is not referenced by a
node, avatar, or retained chat attachment. A zero-candidate run is useful but
is not sufficient evidence to enable deletion. Change the default to `"0"`
only in a dedicated follow-up after at least one representative candidate has
been reviewed.

## Backup and restore drill

After deploying the backup role, trigger a backup and confirm it contains both
the Kizuna PostgreSQL dump and Garage volumes:

```sh
docker exec borgmatic borgmatic --verbosity 1
docker exec borgmatic borgmatic list --archive latest --find '*kizuna*'
```

Restore the database into an isolated PostgreSQL container on
`backend-internal`; never restore over the live Kizuna database for a drill:

```sh
KIZUNA_DRILL_PASSWORD="$(openssl rand -hex 24)"
docker run -d --rm --name kizuna-restore-drill --network backend-internal \
  -e POSTGRES_DB=kizuna_api_production \
  -e POSTGRES_USER=kizuna \
  -e POSTGRES_PASSWORD="$KIZUNA_DRILL_PASSWORD" \
  pgvector/pgvector:pg16
until docker exec kizuna-restore-drill pg_isready -U kizuna \
  -d kizuna_api_production; do sleep 1; done
docker exec borgmatic borgmatic restore --archive latest \
  --database kizuna_api_production \
  --hostname kizuna-restore-drill \
  --username kizuna \
  --password "$KIZUNA_DRILL_PASSWORD"
docker exec kizuna-restore-drill psql -U kizuna -d kizuna_api_production \
  -c 'select count(*) from nodes;'
docker stop kizuna-restore-drill
unset KIZUNA_DRILL_PASSWORD
```

For Garage, extract the latest archive to scratch storage and confirm it
contains the object-data tree plus a recent file under the metadata volume's
`snapshots/` directory. Perform the full Garage recovery in an isolated Compose
project with new volume names and no public Traefik labels, then retrieve a
known captured image through that isolated S3 endpoint. Do not attach restored
volumes to the live stack during a drill.

The deployment is ready for trusted daily use only after both isolated restore
checks pass.
