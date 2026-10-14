# Multi-Scrobbler

Runs on `nuc-mini` with persistent configuration and history under
`/opt/docker/multi-scrobbler/config`. Credentials come from
`group_vars/multi_scrobbler/vault.yml`; see [Secrets](../../docs/secrets.md).

## Configuration identities

The pinned 0.19.2 release requires an explicit `id` for each source and client.
Preserve `plex` and `lastfm`: these match the existing database component UIDs
and retain their history. The Album Sort receiving endpoint uses `album-sort`.

Album Sort submits ListenBrainz-compatible requests to Multi-Scrobbler. Its
source type is `endpointlz`, with the existing `multi_scrobbler_lze_token` used
for local ingress authentication. The `listenbrainz` source type instead polls
an external ListenBrainz account and requires a username; it does not implement
this receiving endpoint.

## Deployment and verification

Before upgrading, stop the container and back up its entire configuration
directory, including `ms.db`, credential files, and caches. Preserve the previous
image. Database migrations can make an image-only rollback insufficient.

Deploy from the repository root:

```sh
make -C deploy multi_scrobbler
```

Check source and client readiness in the application and inspect startup logs
for configuration validation or authentication failures. The Docker health check
only tests the web UI. Verify the Plex source connects, the Last.fm client loads
its existing credentials, and `/1/validate-token` on port 9078 recognizes the
Album Sort endpoint. Do not submit fabricated scrobbles as a health check.
