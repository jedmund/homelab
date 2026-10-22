# Photon

Shared internal service on `nuc-mini`, managed as the `photon` Compose project
in `/opt/docker/photon`. No host ports or Traefik routes are published. Clients
on `backend-internal` reach `photon` through Docker DNS.

## Deployment

The image and US/Japan database are unchanged from the Kizuna deployment.
`photon:2322` is the shared endpoint; `kizuna-geocoder:2322` remains a Docker
network alias so existing Kizuna processes can keep their current URL.
Dawarich's worldwide Photon remains in its own application stack.

After preparing the database, deploy from the repository root:

```sh
make -C deploy photon
```

The role refuses to start while the old `kizuna-geocoder` container exists,
preventing two Photon processes from opening the same database. Both healthy
containers and successful lookups from a client are required for acceptance.

## Moving the services out of Kizuna

This cutover moves both Photon and Valhalla on `nuc-mini`. Preserve
`/srv/kizuna-geocoder`, `/srv/kizuna-router`, their ownership, and both running
image IDs. Do not copy, rebuild, or delete the datasets during extraction.
Save `/opt/docker/kizuna/compose.yaml` in a restricted backup directory first.

1. Stage the revised Kizuna Compose file with only `kizuna-geocoder` and
   `kizuna-router` removed. Verify that all other service definitions are
   unchanged. Do this before stopping either service so Kizuna CI cannot
   recreate the old database owner. Leave the current Kizuna environment files
   in place; the legacy DNS aliases support them during this cutover.
2. On `nuc-mini`, stop and remove only the old geo containers:

   ```sh
   docker stop kizuna-geocoder kizuna-router
   docker rm kizuna-geocoder kizuna-router
   ```

3. From the control machine, deploy the two new roles using their pinned images:

   ```sh
   make -C deploy deploy STACK=photon EXTRA_ARGS='-e docker_pull_policy=missing'
   make -C deploy deploy STACK=valhalla EXTRA_ARGS='-e docker_pull_policy=missing'
   ```

4. Verify both new Compose projects, Docker health, Photon results for the US
   and Japan, and Valhalla pedestrian routes in both countries. Test the new
   DNS names and old aliases from `kizuna-api`. A repeated deployment must
   retain both containers. Register `photon` and `valhalla` in Komodo using
   the repository declarations, and refresh Kizuna's cached service list.
   Preview any Resource Sync before applying it.

Komodo 2.3.3's `RefreshStackCache` refreshes the latest file contents but
preserves the service list from the previous deployment. To reconcile that
list without replacing application containers, first verify that Kizuna's
build, destroy-before-deploy, and pre/post commands are disabled. Save its
current `auto_pull` and `extra_args`, temporarily set `auto_pull = false` and:

```toml
extra_args = ["--no-recreate", "--no-deps", "--pull", "never"]
```

Deploy only the already-running `kizuna-web` service through Komodo, wait for
success, then restore the saved settings. Confirm that the cached deployment
lists only Kizuna's remaining services and that all application container IDs,
start times, and restart counts are unchanged. This updates deployment metadata
without fetching images or restarting the application.

The cutover does not require restarting Kizuna or deploying new application
images. Its next normal deployment writes the configurable shared URLs.
The new geo services have no host ports, public DNS, Traefik route, or secret
inputs. Komodo observes their Docker health; Gatus's public HTTP checks do not
reach these private endpoints.

For rollback, stop and remove the new `photon` and `valhalla` containers first,
restore the saved Kizuna Compose file, then start only `kizuna-geocoder` and
`kizuna-router` with `--pull never`. Verify client queries again. Never run both
Photon containers against the same directory. Keep the backup until acceptance.

## Database and serving

`photon` runs [Photon](https://github.com/komoot/photon) 1.x to turn
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

The JVM heap is `photon_java_heap` (2 GB). Embedded OpenSearch reads
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
   `tmux` or `nohup` with the image from `photon_image`. It needs
   passwordless `sudo` to give the data directory to UID 9011:

   ```sh
   IMG='ghcr.io/rtuszik/photon-docker:2.4.0@sha256:21549c60f9e6488fff3217e40429a652c4b445f374800333fe32859e47cec293'
   mkdir ~/photon-import && cd ~/photon-import
   # copy roles/photon/files/geocoder_import.sh here
   ./geocoder_import.sh "$PWD" "$IMG" 2>&1 | tee import.log
   ```

2. Check the result on max before copying. Start a temporary server on a
   loopback port and query it:

   ```sh
   docker run -d --rm --name photon-check --user 9011:9011 \
     -p 127.0.0.1:2399:2322 -v "$PWD/data:/photon/data" \
     --entrypoint java "$IMG" -Xmx2g -jar /photon/photon.jar serve \
     -data-dir /photon/data -listen-ip 0.0.0.0
   curl -s http://127.0.0.1:2399/status
   for q in '1 Dr Carlton B Goodlett Pl, San Francisco' \
            '東京都 渋谷区 道玄坂 2-29-1' '2-29-1 Dogenzaka, Shibuya, Tokyo'; do
     curl -s -G --data-urlencode "q=$q" -d limit=1 http://127.0.0.1:2399/api
     echo
   done
   docker stop photon-check
   ```

3. Copy the database from max to a staging directory on nuc-mini. max has
   no SSH key for nuc-mini, so run this from a workstation that can reach
   both. Both ends run `tar` with `sudo` so the UID 9011 ownership is
   preserved:

   ```sh
   ssh -p 6768 justin@192.168.1.100 \
       'sudo tar -C ~/photon-import/data -cf - photon_data' \
     | ssh -p 6895 justin@192.168.1.6 \
       'sudo mkdir -p /srv/kizuna-geocoder/staging &&
        sudo tar -C /srv/kizuna-geocoder/staging --numeric-owner -xpf -'
   ```

   On nuc-mini, swap it into place. The geocoder is stopped only for the
   rename:

   ```sh
   cd /opt/docker/photon && docker compose stop photon
   sudo mv /srv/kizuna-geocoder/photon_data /srv/kizuna-geocoder/photon_data.old
   sudo mv /srv/kizuna-geocoder/staging/photon_data /srv/kizuna-geocoder/photon_data
   docker compose start photon
   ```

   For the first build, there is no `photon_data` to move aside and no
   container to stop.

4. Run the checks below, then delete `photon_data.old` and `staging` on
   nuc-mini and `~/photon-import` on max with `sudo rm -rf`; the
   files belong to UID 9011.

### Verify

```sh
docker inspect --format '{{.State.Health.Status}}' photon
docker exec kizuna-api sh -c 'test -n "$WIDGET_GEOCODER_URL"'
docker exec kizuna-worker sh -c 'test -n "$WIDGET_GEOCODER_URL"'
docker exec kizuna-chat-worker sh -c 'test -n "$WIDGET_GEOCODER_URL"'
docker exec kizuna-api curl --fail --silent http://photon:2322/status
docker exec kizuna-api curl --fail --silent \
  'http://photon:2322/api?q=San+Francisco+City+Hall&limit=1'
```
