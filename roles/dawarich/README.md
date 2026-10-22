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

## Verification

Check application health, worker health, and reverse geocoding from both the
web and worker containers using their configured `PHOTON_API_HOST`. Confirm
known country codes and exercise background geocoding before accepting an
application or geocoder upgrade. Never print the complete environment file.

PostGIS user data and Redis are separate from the rebuildable Photon index.
Preserve their existing images, volume identities, and credentials when changing
the geocoder. See [Backup](../backup/README.md) for configured backup coverage.
