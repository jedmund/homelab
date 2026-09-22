# Karakeep

Deploys Karakeep, its browser, and Meilisearch on `nuc-mini` at
`https://keep.atelier.house`. Deployment files live in `/opt/docker/karakeep`.
The named volumes `karakeep-data` and `karakeep-meilisearch` retain application
and search data. Credentials belong in `group_vars/karakeep/vault.yml`.

## Browser image

The role uses `ghcr.io/karakeep-app/karakeep-chrome:release`, upstream's
stable browser channel. The previous `gcr.io/zenika-hub/alpine-chrome` image
is no longer available from its registry. See the
[upstream migration guide](https://docs.karakeep.app/administration/chrome-image-migration/).

The browser requires `init: true`. Its entrypoint supplies `--no-sandbox`
and manages an internal debugging port with forwarding to container port
9222. Do not override the remote-debugging address or port in Compose.
Karakeep connects through `http://karakeep-chrome:9222`; that address does
not change with the browser migration.

Application and browser `release` tags can move. The shared pull policy
checks for updated images on normal deployments. Set explicit image versions
or digests in the role variables when a fixed version is required. Review
Meilisearch upgrades separately; its data compatibility requirements are
independent of replacing the browser.

## Deployment and verification

From the repository root:

```sh
make check
make -C deploy karakeep
```

To apply configuration using cached images where available:

```sh
make -C deploy deploy STACK=karakeep EXTRA_ARGS='-e docker_pull_policy=missing'
```

Check the web and search container health, then verify that the web container
can reach the browser's `/json/version` endpoint on port 9222. Resolve the
browser hostname to its container IP before making a direct debugging request,
as Karakeep's crawler does; Chrome rejects a non-local hostname in that request.
An HTTP check alone does not verify crawling: also test browser navigation and screenshots,
or save a bookmark and confirm that its content and screenshot are captured.

The browser has no persistent data, and this image replacement requires no
database migration. For a browser rollback, restore a compatible image and
its matching Compose command flags together. The old Alpine image requires
explicit remote-debugging flags; the new image must not receive them.
