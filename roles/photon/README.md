# Photon

Shared worldwide forward and reverse geocoder on `nuc-mini`, managed as the
`photon` Compose project in `/opt/docker/photon`. Kizuna and Dawarich use one
Photon 1.3.0 process and the existing `dawarich-photon-data` Docker volume.
The image is pinned by digest in [defaults](defaults/main.yml).

## Clients and networking

The shared endpoint is `http://photon:2322`. The container joins
`backend-internal` for Kizuna and `shared-network` for Dawarich. Existing clients
can retain `kizuna-geocoder:2322` on backend and `dawarich-photon:2322` on shared;
these are network aliases of the same container. No host port, public DNS,
Traefik route, or new credential is required. The shared network permits egress,
but the service runs the jar directly and does not run automatic index updates.

Kizuna writes its configurable `kizuna_geocoder_url` to `WIDGET_GEOCODER_URL`.
Dawarich writes `dawarich_photon_api_host` to `PHOTON_API_HOST`; both default to
`photon:2322`, with the HTTP scheme included only in Kizuna's URL. A subsequent
normal app deployment updates those environment files. The aliases allow the
consolidation to preserve existing app processes and credentials.

## Deployment and data

```sh
make -C deploy photon
```

The worldwide volume is external to Compose. The role verifies that it exists
and contains `photon_data` owned by UID/GID 9011 before changing deployment
files. It does not create an empty replacement volume or change index ownership.
It refuses to start while either application-owned Photon container exists,
preventing two processes from opening the same index or conflicting DNS aliases.

The image, UID/GID, and worldwide index are reused from Dawarich. The Java
launch includes its existing OpenSearch settings with the shared role's explicit
2 GB heap. OpenSearch also uses the host page cache. Monitor lookup latency,
heap pressure, and container memory when changing coverage or query volume.

`dawarich-photon-data` is not included in Borg's named-volume sources. It is a
rebuildable index, not user-authored data. Deployment configuration under
`/opt/docker/photon` is backed up. See [Backup](../backup/README.md).

## Consolidating the regional and worldwide instances

Before cutover, retain both Compose files, running image/container identities,
and the worldwide volume's identity and ownership in a restricted backup
location. Verify forward and reverse lookups in the US, Japan, and a third
country against the existing worldwide service. Both old instances must use a
compatible Photon version. Keep the regional index until client checks pass.

1. Stage Dawarich's revised Compose file with only `dawarich-photon` and its
   old top-level volume declaration removed. Verify all other effective service
   definitions are unchanged. Leave Dawarich's environment files intact. This
   prevents its CI redeployment from recreating another worldwide index owner.
2. Stop `photon` and `dawarich_photon`, then remove only `dawarich_photon`.
   Preserve the existing `dawarich-photon-data` volume. Do not use `down -v`.
3. Deploy the Photon role with its external worldwide volume and both client
   network aliases:

   ```sh
   make -C deploy deploy STACK=photon EXTRA_ARGS='-e docker_pull_policy=missing'
   ```

4. Run the client checks below, including forward and reverse lookups. Confirm
   that Kizuna, Dawarich, their databases/workers, and Valhalla kept their
   container IDs, start times, and restart counts. Repeat the Photon deployment;
   it should report no changes and retain the container ID.
5. Refresh Photon in Komodo and reconcile Dawarich's cached deployed-service
   list. Komodo 2.3.3's `RefreshStackCache` updates latest contents but retains
   the old deployment list. Save Dawarich's `auto_pull` and `extra_args`; verify
   its build, destroy-before-deploy, and pre/post commands are disabled. Set
   `auto_pull = false` and temporarily use:

   ```toml
   extra_args = ["--no-recreate", "--no-deps", "--pull", "never"]
   ```

   Deploy only the already-running `dawarich-app` service through Komodo, wait
   for success, then restore the exact original settings. Verify every app
   container identity again. No full Resource Sync is needed for this cutover.
6. After acceptance, confirm no container mounts `/srv/kizuna-geocoder`, then
   remove its retired regional index to reclaim space. This ends immediate
   rollback to the regional index; it can be rebuilt using the regional helper.

Before regional cleanup, rollback stops the new Photon container, restores the
saved Photon and Dawarich Compose files, and starts only their respective Photon
services with `--pull never`. Never run two processes against the worldwide
volume. Restore Komodo's service list after rollback.

## Verification

From Kizuna, check the shared name and retained alias:

```sh
docker inspect --format '{{.State.Health.Status}}' photon
docker exec kizuna-api curl --fail --silent http://photon:2322/status
docker exec kizuna-api curl --fail --silent http://kizuna-geocoder:2322/status
docker exec kizuna-api curl --fail --silent --get \
  --data-urlencode 'q=1 Dr Carlton B Goodlett Pl, San Francisco' \
  -d limit=1 http://photon:2322/api
docker exec kizuna-api curl --fail --silent --get \
  --data-urlencode 'q=2-29-1 Dogenzaka, Shibuya, Tokyo' \
  -d limit=1 http://photon:2322/api
docker exec kizuna-api curl --fail --silent --get \
  --data-urlencode 'q=Eiffel Tower, Paris' -d limit=1 http://photon:2322/api
```

From both `dawarich_app` and `dawarich_sidekiq`, request `/status` and `/reverse`
using the host in `PHOTON_API_HOST`. Check known coordinates in multiple countries
and verify country codes, not merely HTTP status. Exercise concurrent requests
from both applications before accepting changes to the JVM or worldwide index.
Browser PlaceMaps and Dawarich's background geocoding require their own checks.

## Refreshing the worldwide index

Build or download a compatible worldwide index into a separate staging volume;
never replace files while Photon is serving them. Use the upstream
[Photon import documentation](https://github.com/komoot/photon#installation)
and a dump compatible with the pinned Photon major version. Keep the complete
worldwide coverage and UID/GID 9011. Validate a temporary server using that
volume, including non-US/Japan forward and reverse lookups, before stopping the
shared server and changing `photon_data_volume` to the new external volume.
Retain the previous volume until all clients have passed acceptance.

[`files/geocoder_import.sh`](files/geocoder_import.sh) remains a regional rebuild
helper for the former US/Japan index. Its default country filter is not suitable
for rebuilding the worldwide service. It is available for recovery of the old
regional deployment; do not substitute its output for the shared worldwide index.

Japanese addresses without spaces can match poorly. Compare spaced Japanese
text and romanized addresses when diagnosing search quality; sharing an index
does not change Photon's text segmentation.
