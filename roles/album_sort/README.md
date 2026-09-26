# Album Sort

Deploys Album Sort and its Beets service on `nuc-mini` at
`https://music.sort.atelier.house`. GitLab CI publishes the two images;
Ansible renders the stack under `/opt/docker/album-sort`.

## Configuration

[defaults/main.yml](defaults/main.yml) defines the image references, tag,
OIDC provider, paths, and API settings. Both images use
`album_sort_image_tag`, which defaults to `latest`. CI publishes `latest`
from the default branch and can request a Komodo redeployment. Use a published
commit tag for a deployment freeze or compatible rollback.

Store credentials in `group_vars/album_sort/vault.yml` as described in
[Secrets](../../docs/secrets.md#groupvarsalbumsortvaultyml). Required inputs
include registry access, PocketID credentials, and
`vault_album_sort_user_secret_encryption_key`.

The encryption key is canonical base64 encoding of 32 random bytes. Provision
it once and preserve it across deployments. Keep an encrypted recovery copy
separate from the application database. Changing it invalidates credentials
protected by the old key.

## Deployment

Traefik must be running before Album Sort. The role inspects Traefik's address
on `proxy-network`, checks it against `traefik_proxy_ipv4_address` in inventory,
and configures trust for that single address as a `/32`.

From the repository root:

```sh
make -C deploy syntax STACK=album_sort
make -C deploy album_sort
```

The role renders configuration, logs into the registry, pulls both images,
and waits for the application container to report healthy. Environment changes
request recreation in that same deployment, before the health check; there is
no later Compose restart handler.

Do not pin image IDs or change pull policy in the generated host Compose file.
Set `album_sort_image_tag` in Ansible instead. Both the role and Compose
configuration explicitly pull images; the shared `docker_pull_policy` override
does not freeze this stack.

## Authentication and proxy behavior

The browser interface uses native PocketID OIDC. The current default also
applies TinyAuth to the main browser route.

When `album_sort_expose_rest_api` is enabled, `/rest` has separate routes for
OpenSubsonic clients. These routes bypass browser-oriented TinyAuth. The
application handles protocol authentication.

The HTTPS route overwrites `X-Forwarded-Proto` with `https`. The HTTP route
overwrites it with `http` and has priority `2147482647`, above the configured
Traefik entrypoint redirect priority `2147482646`. This delivers plain HTTP
requests to the application's rejection path rather than redirecting them.
Verify rejection after changes to the proxy or application image.

If the proxy network or Traefik address changes, update the inventory pin and
redeploy Traefik and Album Sort together. The role rejects an absent or
unexpected proxy address. Do not replace the single-address trust rule with
the entire Docker subnet.

## Integrations and storage

| Item | Configuration |
| --- | --- |
| Application state | `/opt/docker/album-sort/data` |
| Beets state | `/opt/docker/album-sort/beets-data` |
| Music | NFS-backed volume mounted at `/music`; default input/output directories are `/music/Sort` and `/music/Sorted` |
| MusicBrainz | `http://musicbrainz:5000/ws/2` on the shared Docker network |
| Cover Art Archive | Public service, configured by `album_sort_cover_art_archive_base_url` |
| Multi-Scrobbler | `album_sort_multi_scrobbler_url`; users enter their own credentials in the application's Music settings |

The environment template supplies `MULTI_SCROBBLER_URL` and
`USER_SECRET_ENCRYPTION_KEY`. It does not inject a shared
`MULTI_SCROBBLER_TOKEN`. Revoking an old shared token is a separate credential
operation.

## Verification and recovery

Check container health, `/healthz`, browser login/logout, protocol discovery,
anonymous private-method rejection, and plain-HTTP `/rest` rejection. Test
personal scrobbling through the owning user's configured account. Keep real
credentials out of test URLs and captured logs.

Back up application state and the encryption key before incompatible upgrades.
For a rollback, select an image compatible with the current database and
credential format. Restore older data only through the application's recovery
procedure. The former M4 cutover verifier is retired.

## Private Storybook registry

Storybook is an independent static catalog managed by the dedicated Komodo Action;
it does not join the application network or require a music root. See the
[Komodo activation runbook](../../komodo/README.md#album-sort-storybook-catalogs).

Registry provisioning is disabled by default. Place
`vault_album_sort_storybook_registry_username` and
`vault_album_sort_storybook_registry_password` in this role's encrypted vault.
After activation is authorized, the `storybook-registry` tag with
`album_sort_storybook_registry_enabled=true` provisions only the dedicated Docker
config. Do not reuse or replace `/etc/komodo/docker/config.json`: Kizuna owns that
shared login. No Storybook service is deployed by this tag.

## Tag preparation concurrency

`album_sort_tag_preflight_concurrency`, `album_sort_tag_staging_concurrency`, and
`album_sort_tag_copy_concurrency` render the corresponding `TAG_*_CONCURRENCY`
environment settings. All default to `1`; valid values are `1`, `2`, and `4`, with
copies no greater than staging workers. Invalid settings fail before host changes.
These require an application image with bounded tag preparation support.

Use one pinned application build for baseline `1/1/1` and candidate `2/2/1`.
Change settings only after active work drains. Deploy through the existing Compose
lifecycle, then verify health, the `Tag concurrency configuration` log and completed
startup scanning. Keep the existing music volume, NFSv3 and NAS Sync mode. Staging
files remain beside their originals.

Measurements use user-approved normal album matches, never automated tag edits or
undo on the library. Collect three FLAC, one AAC, one ALAC and one MP3 match per
profile with application timing logs and read-only NUC CPU/network and NFS
latency/retransmission samples. Match format/edit type and track count/size within
25%; flag storage contention and unmatched samples. The application repository's
`docs/tag-write-timings.md` owns the comparison command and decision procedure.

Retain two workers provisionally only with at least 15% lower median apply
seconds/MiB for comparable FLAC and M4A samples, at most 10% preview seconds/file
regression and clean correctness checks. Otherwise keep sequential defaults and
collect three additional comparable pairs; remain sequential if inconclusive.
On verification/recovery failure or persistent degradation, stop the trial, drain
active work, restore all three settings to `1`, and redeploy the same image.
Preserve journals for normal recovery. Merging configuration does not authorize
deployment or the trial.
