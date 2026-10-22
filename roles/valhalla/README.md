# Valhalla

Shared internal service on `nuc-mini`, managed as the `valhalla` Compose project
in `/opt/docker/valhalla`. No host ports or Traefik routes are published. Clients
on `backend-internal` reach `valhalla` through Docker DNS.

## Deployment

The shared endpoint is `http://valhalla:8002`. The `kizuna-router` network alias
keeps existing Kizuna URLs working. The image, US/Japan tiles, runtime user,
thread count, and cache limit are preserved from the Kizuna deployment.

Deploy from the repository root after preparing all three dataset files:

```sh
make -C deploy valhalla
```

The role checks for the tile archive, admin database, and timezone database
before deploying. It refuses to start while the old `kizuna-router` container
exists. On an existing host, follow the shared [Kizuna cutover](../photon/README.md#moving-the-services-out-of-kizuna)
first. Keep the data mount read-only and verify actual routes as well as health.

## Tiles and serving

`valhalla` runs [Valhalla](https://github.com/valhalla/valhalla) to give
route PlaceMaps walking paths with per-leg distance and time. The API calls
`POST /route` with `costing: pedestrian`, one attempt with a 5 s timeout; a
blank `WIDGET_ROUTER_URL` in `templates/env/api.env.j2` disables routing and
legs fall back to straight-line estimates. The service joins only the
internal `backend` network, so it has no egress and no Traefik route.

The image is the official `ghcr.io/valhalla/valhalla`, pinned by tag and
digest in [defaults](defaults/main.yml). It has no image user, so Compose
runs it as the shared runtime user (`puid`/`pgid`). On every start, the
container generates its configuration with the image's
`valhalla_build_config`, so the configuration matches the Valhalla version,
then serves `valhalla_tiles.tar` from `/srv/kizuna-router`, mounted read-only.
The directory is outside `/opt/docker`, so Borg does not back it up; it is
rebuilt from the upstream extracts. The role stops before deploying if the
tile archive is missing.

Valhalla was chosen over GraphHopper and OSRM because it reads the tile
archive through `mmap` with a bounded cache (`valhalla_cache_bytes`).
GraphHopper and OSRM load the whole routing graph into process memory, which
for the United States does not fit next to the rest of nuc-mini.

Measured on 2026-10-16 with Geofabrik extracts of that day: the build on max
took 31 minutes and needed 14.8 GB of extracts plus at least 90 GB of
intermediate tiles. The result is 23 GiB (`valhalla_tiles.tar`, 18,677 tiles)
plus 141 MB of admin and timezone databases. On nuc-mini, Valhalla answered
`/status` within a second of starting with a resident size of about 215 MiB.
A four-leg 3.3 km loop and a two-leg 2.7 km route took 20–70 ms, including
with eight requests at once.

There is no elevation data, so walking time is a flat rate and steep routes
are underestimated. Adding elevation (`valhalla_build_elevation`) is a
separate change.

### Build or refresh the tiles

Build the tiles on max, then copy them to nuc-mini. Refresh when map data is
noticeably stale or after a Valhalla upgrade that changes the tile format
(read the release notes).

[`files/router_build.sh`](files/router_build.sh) runs the build. It downloads
`us-latest.osm.pbf` and `japan-latest.osm.pbf` from Geofabrik and checks
their MD5 sums. `valhalla_build_tiles` reads each extract several times, so
they are stored in the scratch directory rather than streamed. It then builds
the timezone and admin databases and the tiles, writes the tile archive, and
deletes the extracts and intermediate tiles. Valhalla warns that building
from more than one extract is discouraged; that concerns overlapping
extracts with duplicate OSM IDs, and these two do not overlap. The admin
`NOT NULL constraint failed` errors are expected for a non-planet build.

1. On max, copy the script into a new scratch directory with at least 120 GB
   free and run it under `tmux` or `nohup` with the image from
   `valhalla_image`:

   ```sh
   IMG='ghcr.io/valhalla/valhalla:3.9.1@sha256:4fd114eb1d26b8fc2f43bcb3df234c1b63a0bf13c277405e5943d5361dc575de'
   mkdir ~/valhalla-build && cd ~/valhalla-build
   # copy roles/valhalla/files/router_build.sh here
   ./router_build.sh "$PWD" "$IMG" 2>&1 | tee build.log
   ```

2. Check the result on max before copying:

   ```sh
   docker run -d --rm --name valhalla-check --user "$(id -u):$(id -g)" \
     -p 127.0.0.1:8099:8002 -v "$PWD/out:/data:ro" "$IMG" bash -ec '
       valhalla_build_config --mjolnir-tile-extract /data/valhalla_tiles.tar \
         --mjolnir-admin /data/admins.sqlite \
         --mjolnir-timezone /data/timezones.sqlite \
         --httpd-service-listen tcp://0.0.0.0:8002 > /tmp/valhalla.json
       exec valhalla_service /tmp/valhalla.json 4'
   curl -s http://127.0.0.1:8099/status
   curl -s http://127.0.0.1:8099/route -H 'Content-Type: application/json' -d '
     {"locations": [{"lat": 37.7793, "lon": -122.4193},
                    {"lat": 37.7955, "lon": -122.3937}],
      "costing": "pedestrian", "directions_type": "none"}'
   curl -s http://127.0.0.1:8099/route -H 'Content-Type: application/json' -d '
     {"locations": [{"lat": 35.6596, "lon": 139.6987},
                    {"lat": 35.6717, "lon": 139.7032}],
      "costing": "pedestrian", "directions_type": "none"}'
   docker stop valhalla-check
   ```

3. From a workstation that can reach both hosts, copy the files to a staging
   directory on nuc-mini and give them to the runtime user:

   ```sh
   ssh -p 6768 justin@192.168.1.100 \
       'tar -C ~/valhalla-build/out -cf - \
          valhalla_tiles.tar admins.sqlite timezones.sqlite' \
     | ssh -p 6895 justin@192.168.1.6 \
       'sudo mkdir -p /srv/kizuna-router/staging &&
        sudo tar -C /srv/kizuna-router/staging -xf - &&
        sudo chown -R 977:988 /srv/kizuna-router/staging'
   ```

   On nuc-mini, swap the files into place. The router is stopped only for
   the rename:

   ```sh
   cd /opt/docker/valhalla && docker compose stop valhalla
   cd /srv/kizuna-router
   for f in valhalla_tiles.tar admins.sqlite timezones.sqlite; do
     sudo mv "staging/$f" "$f"
   done
   sudo rmdir staging
   cd /opt/docker/valhalla && docker compose start valhalla
   ```

   For the first build, extract straight into `/srv/kizuna-router` and skip
   the swap.

4. Run the checks below, then delete `~/valhalla-build` on max.

### Verify the router

```sh
docker inspect --format '{{.State.Health.Status}}' valhalla
docker exec kizuna-api sh -c 'test -n "$WIDGET_ROUTER_URL"'
docker exec kizuna-worker sh -c 'test -n "$WIDGET_ROUTER_URL"'
docker exec kizuna-api curl --fail --silent http://valhalla:8002/status
```
