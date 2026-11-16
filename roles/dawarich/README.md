# Dawarich

Location-history application on `nuc-mini`. Its Compose project owns the web
app, Sidekiq worker, PostGIS, and Redis. Forward/reverse geocoding is supplied
by the independent shared [Photon](../photon/README.md) stack.

## Deployment

Deploy Photon first, then this role:

```sh
make -C deploy photon
make -C deploy dawarich
```

`dawarich_photon_api_host` defaults to `photon:2322` and
`dawarich_photon_api_use_https` to `false`. Both web and Sidekiq receive these
through the shared environment file. The old `dawarich-photon` hostname remains
an alias on `shared-network`, so existing containers do not need restarting
during the geocoder consolidation. The app no longer owns the geocoder service
or declares its volume.

The worldwide `dawarich-photon-data` volume remains intact and is external to
Photon's Compose lifecycle. Follow the [consolidation procedure](../photon/README.md#consolidating-the-regional-and-worldwide-instances)
before deploying this change onto a host with the old geocoder container.

## Upgrades

`dawarich_image` follows `latest`, and upstream publishes no major-version tag.
A deploy that pulls a new image upgrades Dawarich, possibly across several
releases. Releases can include migrations that cannot be rolled back,
background jobs that rewrite data, and image or Compose changes. Before a
deploy that pulls a newer image:

1. Read the upgrade notes of every release between the running version and the
   target on the [releases page](https://github.com/Freika/dawarich/releases).
   Apply image, Compose, and environment changes in this role before
   deploying. The running version is the image's
   `org.opencontainers.image.version` label:
   `ssh nuc 'docker inspect dawarich_app --format "{{index .Config.Labels \"org.opencontainers.image.version\"}}"'`.
2. Dump the database. The nightly backup also dumps it, but a dump taken
   immediately before the upgrade is the rollback point:

   ```sh
   ssh nuc 'docker exec dawarich_postgres pg_dump -U dawarich -Fc dawarich_production > /opt/docker/dawarich/pre-upgrade.dump'
   ```

3. Stop the worker so it releases its locks on `points`. Some migrations wait
   only a few seconds for that lock and stop with a lock timeout otherwise:

   ```sh
   ssh nuc 'docker stop -t 60 dawarich_sidekiq'
   ```

4. Deploy. The app runs migrations on start, and the worker starts only after
   the app reports healthy. Long migrations can outlast the healthcheck window
   and fail the deploy while they continue. Follow `docker logs -f dawarich_app` until the app is
   healthy, then deploy again to start the worker.
5. Leave the worker running afterward. Post-upgrade background jobs can take a
   long time to finish.
6. Delete `pre-upgrade.dump` once the upgrade is verified.

To roll back across an irreversible migration, restore the dump into an empty
database and deploy with `-e dawarich_image=freikin/dawarich:<previous version>`.

## Verification

Check application health, worker health, and reverse geocoding from both the
web and worker containers using their configured `PHOTON_API_HOST`. Confirm
known country codes and exercise background geocoding before accepting an
application or geocoder upgrade. Never print the complete environment file.

PostGIS user data and Redis are separate from the rebuildable Photon index.
Preserve their existing images, volume identities, and credentials when changing
the geocoder. See [Backup](../backup/README.md) for configured backup coverage.
