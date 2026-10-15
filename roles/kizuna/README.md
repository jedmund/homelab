# Kizuna production runbook

The public deployment probes in the API and app pipelines verify that Komodo
finished successfully, the exact commit is live, the SPA deep-link fallback
works, API credentialed CORS is correct, and the private Garage endpoint accepts
the expected upload preflight. The checks below cover the authenticated and
stateful behavior that should not be automated with production credentials.

## iOS OIDC client

Set `vault_kizuna_oidc_public_client_id` in `group_vars/kizuna/vault.yml`
to the iOS public OIDC client ID. The role maps it through
`kizuna_ios_oidc_client_id` to `KIZUNA_IOS_OIDC_CLIENT_ID` in the shared
API and worker environment file. It defaults to an empty string when unset.
The web client continues to use `vault_kizuna_oidc_client_id` and
`vault_kizuna_oidc_client_secret`.

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

The local-to-NAS migration has completed on `nuc-mini`. Routine deployment
creates the NAS directory and volume, but no longer stops services or copies
the old local data. See [retired migrations](../../docs/retired-migrations.md)
for completion evidence and the archived implementation.

The old local volume is a historical snapshot, not a current rollback copy.
Setting `kizuna_garage_data_nas_enabled: false` selects that local volume;
returning to local storage requires a separate consistent transfer of current
data before redeployment. Retain the old volume until uploads, archived
playback, and a Garage integrity check have all passed:

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

## PDF visual understanding

The Kizuna role points PDF OCR at the shared Unlimited-OCR service on `max`.
It also controls the two later stages of visual PDF support independently:

- `kizuna_pdf_visual_enrichment_mode` controls semantic descriptions of page
  images. Supported rollout values are `off`, `report`, and `on`.
- `kizuna_pdf_visual_retrieval_enabled` controls whether chat may inspect a
  rendered source page when the retrieved text is insufficient.

Production enables both settings (`on` and `true`). They are non-secret
settings in `roles/kizuna/defaults/main.yml`; no vault update is required.
Before deploying, configure and enable the PDF visual enrichment task in
Kizuna Admin with a shared image-capable model, and configure an image-capable
chat model for page-image retrieval.

Validate the deployment as follows:

1. Deploy the defaults and verify the API and PDF worker received their
   settings without printing the full environment:

   ```sh
   docker exec kizuna-api sh -c \
     'test "$KIZUNA_PDF_VISUAL_ENRICHMENT_MODE" = on && test "$KIZUNA_PDF_VISUAL_RETRIEVAL_ENABLED" = true'
   docker exec kizuna-pdf-worker sh -c \
     'test -n "$KIZUNA_PDF_OCR_BASE_URL" && test "$KIZUNA_PDF_OCR_MODEL" = unlimited-ocr'
   ```

2. Run a content-free canary against an image-heavy PDF. The known production
   canary is node `019ff533-1897-704a-b3ee-f4d5f29436ed`:

   ```sh
   docker exec kizuna-api env ACTION=ocr_repair NODE_ID=019ff533-1897-704a-b3ee-f4d5f29436ed bin/rails pdfs:visual_backfill
   docker exec kizuna-api env ACTION=ocr_repair NODE_ID=019ff533-1897-704a-b3ee-f4d5f29436ed APPLY=1 bin/rails pdfs:visual_backfill
   docker exec kizuna-api env ACTION=visual NODE_ID=019ff533-1897-704a-b3ee-f4d5f29436ed bin/rails pdfs:visual_backfill
   docker exec kizuna-api env ACTION=visual NODE_ID=019ff533-1897-704a-b3ee-f4d5f29436ed APPLY=1 bin/rails pdfs:visual_backfill
   docker exec kizuna-api env NODE_ID=019ff533-1897-704a-b3ee-f4d5f29436ed PAGE_NUMBERS=5,7,8,9 bin/rails pdfs:visual_probe
   ```

   The commands report opaque IDs, counts, and cursors rather than document
   content. Review the probe result and worker health before continuing.

3. Verify that image-heavy PDFs build useful passages and answer questions
   from their semantic descriptions.
4. Verify chat can inspect an actual page when needed and that the answer cites
   the PDF.

To stop new semantic enrichment, restore the mode to `off`. To disable page
inspection independently, restore retrieval to `false`. Existing OCR text and
semantic descriptions remain available for retrieval after either rollback.

## Chat widgets

`kizuna-widget-compiler` compiles model-written OpenUI Lang into the stored
widget tree for `AiWidgetJob`. It joins only the internal `backend` network,
so it has no egress and no Traefik route. The image is built by kizuna-app CI
as `registry.atelier.house/kizuna/kizuna-app/widget-compiler`; `latest` is
published only from the kizuna-app default branch. It must exist before this
role deploys, because the Compose deployment pulls it and waits for its
health check.

Add the shared secret to the Kizuna vault before deploying. Generate it once
with `openssl rand -hex 32`:

```yaml
vault_kizuna_widget_compiler_secret: generated-hex-value
```

The role renders it as `WIDGET_COMPILER_SECRET` in both
`env/widget-compiler.env` and the shared API and worker environment file,
together with `WIDGET_COMPILER_URL=http://kizuna-widget-compiler:4100`. A
blank URL in the API disables widgets; a blank secret disables the sidecar's
header check.

After deployment, verify the container is healthy, the API received both
settings, and the API can reach the sidecar, without printing the secret:

```sh
docker inspect --format '{{.State.Health.Status}}' kizuna-widget-compiler
docker exec kizuna-api sh -c \
  'test -n "$WIDGET_COMPILER_URL" && test -n "$WIDGET_COMPILER_SECRET"'
docker exec kizuna-worker sh -c \
  'test -n "$WIDGET_COMPILER_URL" && test -n "$WIDGET_COMPILER_SECRET"'
docker exec kizuna-api curl --fail --silent http://kizuna-widget-compiler:4100/health
```

To disable widgets without removing the sidecar, blank
`WIDGET_COMPILER_URL` in `templates/env/api.env.j2` and redeploy.

## Geocoder

`kizuna-geocoder` runs [Photon](https://github.com/komoot/photon) 1.x to turn
PlaceMap addresses into coordinates. The API calls
`GET /api?q=<address>&limit=1` with a 3 s timeout and one attempt; a blank
`WIDGET_GEOCODER_URL` in `templates/env/api.env.j2` disables lookups and
places render as cards without pins. The service joins only the internal
`backend` network, so it has no egress and no Traefik route.

The image is `ghcr.io/rtuszik/photon-docker`, pinned by tag and digest in
[defaults](defaults/main.yml). Tag 2.4.0 contains the upstream
`photon-1.3.0.jar` on a Temurin 21 JRE. Compose runs the jar directly as the
image's `photon` user (UID/GID 9011); the image's Python process manager,
which downloads and replaces databases on its own schedule, is not used.

Photon serves a US and Japan database from `/srv/kizuna-geocoder/photon_data`
on nuc-mini. The directory is outside `/opt/docker`, so Borg does not back it
up; it is rebuilt from the upstream dump. The role stops before deploying if
`photon_data` is missing, because Photon cannot build its database at startup
and the Compose wait would otherwise time out.

The JVM heap is `kizuna_geocoder_java_heap` (2 GB). Embedded OpenSearch reads
the index through the page cache, outside the heap.

Measured on 2026-10-15 with the 2026-10-10 dump: the import on max processed
57.6 million documents in 31 minutes, and the database is 15.4 GiB
(15,800 MiB). On nuc-mini, Photon answered `/status` 7 s after start with a
resident size of 1.9 GiB. The first lookup of each address took 0.07–0.58 s; repeated
lookups took 0.02–0.13 s.

Japanese addresses written without spaces match poorly, because Photon does
not segment Japanese text: `東京都渋谷区道玄坂2-29-1` returns a building in
Bunkyō, while `東京都 渋谷区 道玄坂 2-29-1` and
`2-29-1 Dogenzaka, Shibuya, Tokyo` return the correct building.

### Build or refresh the database

Build the database on max, which has the CPU, memory, and disk for the
import, then copy it to nuc-mini. The dump's major version must match the
Photon major version in the image: use `photon-dump-planet-1.0-latest`
with Photon 1.x. Upstream republishes the dump periodically at
<https://download1.graphhopper.com/public/>. Refresh when addresses are
missing from lookups or after a Photon major upgrade.

[`files/geocoder_import.sh`](files/geocoder_import.sh) runs the import. It
fetches the 27 GB compressed dump in ordered 256 MiB range chunks, eight at a
time, because one connection to the download server can fall to about
2 MB/s. Each chunk is decompressed, filtered, and deleted in order, so the
full dump is never stored. `grep` drops lines for other countries before
Photon parses them; Photon still applies `-country-codes us,jp`.
`-languages en,ja` stores English and Japanese name translations in addition
to each place's local name. The script exits non-zero if any stage or chunk
fetch failed. Discard the data directory and run it again in that case:
Photon can exit successfully on truncated input, and the dump is sorted by
country, so a partial database silently lacks `us`.

1. On max, copy the script into a new scratch directory and run it under
   `tmux` or `nohup` with the image from `kizuna_geocoder_image`. It needs
   passwordless `sudo` to give the data directory to UID 9011:

   ```sh
   IMG='ghcr.io/rtuszik/photon-docker:2.4.0@sha256:21549c60f9e6488fff3217e40429a652c4b445f374800333fe32859e47cec293'
   mkdir ~/kizuna-geocoder-import && cd ~/kizuna-geocoder-import
   # copy roles/kizuna/files/geocoder_import.sh here
   ./geocoder_import.sh "$PWD" "$IMG" 2>&1 | tee import.log
   ```

2. Check the result on max before copying. Start a temporary server on a
   loopback port and query it:

   ```sh
   docker run -d --rm --name kizuna-geocoder-check --user 9011:9011 \
     -p 127.0.0.1:2399:2322 -v "$PWD/data:/photon/data" \
     --entrypoint java "$IMG" -Xmx2g -jar /photon/photon.jar serve \
     -data-dir /photon/data -listen-ip 0.0.0.0
   curl -s http://127.0.0.1:2399/status
   for q in '1 Dr Carlton B Goodlett Pl, San Francisco' \
            '東京都 渋谷区 道玄坂 2-29-1' '2-29-1 Dogenzaka, Shibuya, Tokyo'; do
     curl -s -G --data-urlencode "q=$q" -d limit=1 http://127.0.0.1:2399/api
     echo
   done
   docker stop kizuna-geocoder-check
   ```

3. Copy the database from max to a staging directory on nuc-mini. max has
   no SSH key for nuc-mini, so run this from a workstation that can reach
   both. Both ends run `tar` with `sudo` so the UID 9011 ownership is
   preserved:

   ```sh
   ssh -p 6768 justin@192.168.1.100 \
       'sudo tar -C ~/kizuna-geocoder-import/data -cf - photon_data' \
     | ssh -p 6895 justin@192.168.1.6 \
       'sudo mkdir -p /srv/kizuna-geocoder/staging &&
        sudo tar -C /srv/kizuna-geocoder/staging --numeric-owner -xpf -'
   ```

   On nuc-mini, swap it into place. The geocoder is stopped only for the
   rename:

   ```sh
   cd /opt/docker/kizuna && docker compose stop kizuna-geocoder
   sudo mv /srv/kizuna-geocoder/photon_data /srv/kizuna-geocoder/photon_data.old
   sudo mv /srv/kizuna-geocoder/staging/photon_data /srv/kizuna-geocoder/photon_data
   docker compose start kizuna-geocoder
   ```

   For the first build, there is no `photon_data` to move aside and no
   container to stop.

4. Run the checks below, then delete `photon_data.old` and `staging` on
   nuc-mini and `~/kizuna-geocoder-import` on max with `sudo rm -rf`; the
   files belong to UID 9011.

### Verify

```sh
docker inspect --format '{{.State.Health.Status}}' kizuna-geocoder
docker exec kizuna-api sh -c 'test -n "$WIDGET_GEOCODER_URL"'
docker exec kizuna-worker sh -c 'test -n "$WIDGET_GEOCODER_URL"'
docker exec kizuna-api curl --fail --silent http://kizuna-geocoder:2322/status
docker exec kizuna-api curl --fail --silent \
  'http://kizuna-geocoder:2322/api?q=San+Francisco+City+Hall&limit=1'
```

## First acceptance pass

1. Deploy this role and the backup role, then merge one API or app change so its
   default-branch pipeline exercises the Komodo completion and revision gates.
2. Confirm `docker compose ps` reports the API, Postgres, Redis,
   screenshotter, widget compiler, and geocoder as healthy. Confirm both
   workers are running.
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
