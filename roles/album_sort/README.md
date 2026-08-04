# Album Sort

This role deploys the Album Sort application and its Beets sidecar. Album Sort
uses native PocketID/OIDC authentication and reaches Prowlarr, qBittorrent, and
slskd over `shared-network`.

## Acquisition storage zones

The container has three distinct filesystem ownership zones:

- `/downloads` is the existing external `downloads` volume, mounted read-only.
  qBittorrent and slskd own this content; Album Sort only observes and copies it.
- `/quarantine` is the writable `./quarantine` bind mount owned by Album Sort.
  Completed connector downloads land here for intake review.
- `/music/Sort` and `/music/Sorted` are the existing app-managed library roots.

Keep these paths disjoint. Album Sort validates the boundaries at startup and
refuses to boot if a client-owned path overlaps an app-managed path.

## Required vault values

Add these entries to `group_vars/album_sort/vault.yml`:

```yaml
vault_album_sort_prowlarr_api_key: "<Prowlarr Settings > General API key>"
vault_album_sort_qbittorrent_username: "<qBittorrent WebUI username>"
vault_album_sort_qbittorrent_password: "<qBittorrent WebUI password>"
vault_album_sort_slskd_api_key: "<random secret, 16-255 characters>"
```

The slskd key is rendered into both containers. A simple primary slskd API key
has the Administrator role required to search, enqueue, and cancel downloads.
The role intentionally fails before deployment if any connector credential is
missing or the slskd key is too short.

## Deploy and bootstrap

Deploy slskd first so its API key is active before Album Sort tests it:

```bash
make deploy-slskd
make deploy-album-sort
```

One-time operator steps after deployment:

1. In qBittorrent, create the category `album-sort` with save path
   `/downloads/album-sort`.
2. Sign in at `https://music.sort.atelier.house`, then open
   `/settings/connectors` and run all three connection tests. The fields are
   environment-managed; do not save duplicate keys in the UI database.
3. Verify logout and an unauthenticated redirect in a private browser window.
   Native OIDC is now the only application middleware; temporarily set
   `album_sort_use_tinyauth: true` and redeploy only as an auth rollback.
4. Invite the beta users in PocketID. New identities begin as `requester`;
   promote curators and at least one additional owner under `/settings/users`.
5. Run one torrent and one Soulseek acquisition through completed handoff,
   intake admission, organization, and request fulfillment. Confirm the
   qBittorrent source remains present and seeding after handoff.
6. Run the global and per-area kill-switch drills, restore every switch, then
   create and archive an Album Sort backup before opening the cohort.

