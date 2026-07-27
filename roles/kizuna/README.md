# Kizuna production runbook

The public deployment probes in the API and app pipelines verify that Komodo
finished successfully, the exact commit is live, the SPA deep-link fallback
works, API credentialed CORS is correct, and the private Garage endpoint accepts
the expected upload preflight. The checks below cover the authenticated and
stateful behavior that should not be automated with production credentials.

## YouTube enrichment and archival

Add the server-side YouTube Data API v3 key to the Kizuna vault before
deploying:

```yaml
vault_kizuna_youtube_api_key: your-restricted-server-key
```

The role enables video archival by default and shares the resulting settings
with Rails and both Sidekiq containers. `kizuna-worker` consumes only the
default queue; `kizuna-media-worker` consumes only the media queue at
concurrency 1. The media worker uses Deno, yt-dlp with its EJS support package,
and ffmpeg from the Kizuna API image to store an MP4, poster, and selected
captions in the existing Garage bucket. Subtitle selection defaults to
`en.*,en`; override `kizuna_video_archive_sub_langs` in inventory if needed.

For videos that require an authenticated YouTube session, optionally store the
contents of a Netscape-format cookies file in the vault:

```yaml
vault_kizuna_youtube_cookies: |
  # Netscape HTTP Cookie File
  ...
```

The role writes that credential to a mode-`0600` host file and mounts it
read-only into both worker containers. The media worker copies it to an
ephemeral, mode-`0600` path before starting Sidekiq because yt-dlp persists
refreshed cookies when it exits; the host credential remains protected from
container writes. Leave it unset for anonymous yt-dlp access. Never commit the
API key or cookie contents outside the encrypted vault.

After deployment, verify the worker received the non-secret switches and a
non-empty key without printing the credential:

```sh
docker exec kizuna-worker sh -c \
  'test -n "$KIZUNA_YOUTUBE_API_KEY" && test "$KIZUNA_VIDEO_ARCHIVE_ENABLED" = 1'
docker exec kizuna-media-worker sh -c \
  'test -n "$KIZUNA_YOUTUBE_API_KEY" && test "$KIZUNA_VIDEO_ARCHIVE_ENABLED" = 1 && test -w /tmp/kizuna-youtube-cookies.txt && deno --version >/dev/null && yt-dlp --version >/dev/null && python3 -m pip show yt-dlp-ejs >/dev/null'
```

## NAS-backed media storage

Garage continues to provide the private S3 API and presigned playback URLs,
but its large object-block directory is stored under
`Files/Kizuna/Garage` on the NAS. Garage's SQLite metadata stays in the
local `kizuna_kizuna-garage-meta` volume because database metadata should not
live on NFS.

The first deployment performs a one-time, consistent migration:

1. Create the NAS subdirectory and dedicated `kizuna-garage-data-nas` NFS
   volume.
2. Stop the API, both workers, and Garage briefly.
3. Copy the existing `kizuna_kizuna-garage-data` contents to the NAS.
4. Record a migration marker and start the stack against the NAS volume.

The old local volume is deliberately retained as a rollback copy. To roll
back, set `kizuna_garage_data_nas_enabled: false` and redeploy. Remove the old
volume only after uploads, archived playback, and a Garage integrity check
have all passed:

```sh
docker volume inspect kizuna-garage-data-nas
docker exec kizuna-garage /garage status
docker exec kizuna-garage /garage stats
```

Because the object blocks now live on the NAS, the NUC-local Borg repository
backs up only Garage metadata; it no longer duplicates the unbounded media
library. The `Files/Kizuna/Garage` directory therefore needs to be included
in the NAS's own snapshot or offsite-backup policy.

## Web search

SearXNG is deployed by `roles/ai` on `max`; Kizuna reuses it and does not run
a second search container on `nuc-mini`. The endpoint is derived from the
`max` inventory address plus `kizuna_searxng_port`, not a duplicated IP
literal. After every healthy Compose deployment, the Kizuna role runs the
API's idempotent `agent_tools:provision` task. Enabling probes the shared
JSON search endpoint before changing the database, so a failed probe stops
the Ansible run while leaving the running stack and prior connection intact.

Verify the non-secret connection state and probe from inside the API:

```sh
docker exec kizuna-api bin/rails runner \
  'puts AiToolConnection.where(user_id: nil, kind: "searxng").pick(:base_url, :enabled, :last_status).inspect'

docker exec kizuna-api bin/rails runner \
  'connection = AiToolConnection.where(user_id: nil, kind: "searxng").sole; result = AiToolConnections::SearxngClient.new(connection).probe; abort(result.error) unless result.ok?; puts "ok"'
```

Do not print `api_key` or dump the container environment. Confirm
`docker compose -f /opt/docker/kizuna/compose.yaml ps` remains healthy and
that no Kizuna-owned SearXNG container exists on `nuc-mini`. Then sign in and
ask chat for current information; the completed run should have at least one
`AiSource` with `kind: "web"` and a working citation. A second
`make deploy-kizuna` should report the provisioning task unchanged. Open
WebUI and Vane continue to use this same shared service.

To roll back, set `kizuna_searxng_enabled: "false"` and redeploy. Provisioning
skips the probe, disables the instance connection, and Kizuna stops
advertising `web_search`. This does not change the shared SearXNG deployment
or its Open WebUI/Vane consumers.

## First acceptance pass

1. Deploy this role and the backup role, then merge one API or app change so its
   default-branch pipeline exercises the Komodo completion and revision gates.
2. Confirm `docker compose ps` reports the API, Postgres, Redis, and
   screenshotter as healthy. Confirm both workers are running.
3. Sign in through PocketID. Sign out and back in with the password path as a
   second check when password login is enabled.
4. Create and edit a two-line note, reload it, and confirm autosave preserved
   the content. Turn a note into a task; exercise date, time, and priority.
5. Capture a generic link, an image, and a public YouTube URL. Confirm the link
   preview completes, the image survives a reload, and the video receives its
   title, channel, duration, and poster. Confirm the worker eventually marks
   its local copy ready and playback prefers the archived media.
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
