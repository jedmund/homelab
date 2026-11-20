# Mastodon

Deploys glitch-soc at `https://fireplace.cafe` on `nuc-mini`. The `social`
stack contains web, Sidekiq, streaming, PostgreSQL, and Redis services.
Deployment files are stored in `/opt/docker/social`.

## Configuration

Application and streaming images follow glitch-soc's `latest` tags in
[defaults](defaults/main.yml). Web and Sidekiq share the application image.
Both image names are excluded from Renovate so it does not propose pins.

Store credentials in `group_vars/social/vault.yml`; see
[Secrets](../../docs/secrets.md#groupvarssocialvaultyml). Preserve the three
`mastodon_active_record_encryption_*` values across deployments. The role
checks that they are present before writing files and passes them to the
application as `ACTIVE_RECORD_ENCRYPTION_*` environment variables.

## Deployment and upgrades

Resolve both `latest` tags and read the glitch-soc release notes for the target
and every skipped release. Confirm both images belong to the same release.
Take a fresh PostgreSQL custom-format dump and retain the deployed Compose
file, environment files, image IDs, and resolved digests before upgrading. Store these files
with restricted permissions outside the repository.

Ansible uses the shared `always` pull policy. A manual Komodo deployment with
image pulling enabled also updates the application and streaming images.
Komodo reads `/opt/docker/social/compose.yaml`; render the updated references
on the host before using Komodo to update the stack. Automatic updates remain
disabled.

To deploy through Ansible, run from the repository root:

```sh
make check
make -C deploy social
```

The playbook waits up to 180 seconds for Compose health checks. It does not
run database migrations; perform any migration required by the release notes
as a separate upgrade step.

## Upgrading from 4.7.2 to 4.7.3

The [4.7.3 release notes](https://github.com/glitch-soc/mastodon/releases/tag/v4.7.3)
require restarting all Mastodon processes when using Docker. Update both image
references and deploy the role to recreate web, Sidekiq, and streaming with the
new images. The published images include compiled assets; no database migration
is required for this update. Keep PostgreSQL and Redis on their existing images
when performing this application update.

## Upgrading from 4.6 to 4.7

The [4.7.0 release notes](https://github.com/glitch-soc/mastodon/releases/tag/v4.7.0)
require pre-deployment and post-deployment migrations. These can take a long
time on large databases. The [4.7.2 release notes](https://github.com/glitch-soc/mastodon/releases/tag/v4.7.2)
add security fixes without additional migration steps.

After taking the backup, pull the target glitch-soc application and streaming
images. Run pre-deployment migrations with the target application image,
using the existing stack's environment, volumes, and networks:

```sh
# On nuc-mini, with a Compose override selecting the target web image:
docker compose --project-directory /opt/docker/social \
  -f /opt/docker/social/compose.yaml -f /path/to/upgrade.yaml \
  run --rm --no-deps -e SKIP_POST_DEPLOYMENT_MIGRATIONS=true \
  mastodon-web bundle exec rails db:migrate
```

The override contains only the target image:

```yaml
services:
  mastodon-web:
    image: ghcr.io/glitch-soc/mastodon:v4.7.2
```

Once this succeeds, deploy the updated role. Then run post-deployment
migrations on the host:

```sh
cd /opt/docker/social
docker compose run --rm --no-deps mastodon-web bundle exec rails db:migrate
docker compose run --rm --no-deps mastodon-web bundle exec rails db:migrate:status
```

All migration statuses should be `up`. Preserve the Active Record encryption
keys: 4.7 uses them to encrypt local account signing keys in the database.

## Verification

After deployment, verify all five containers are healthy and check:

```sh
curl --fail https://fireplace.cafe/health
curl --fail https://fireplace.cafe/api/v2/instance
```

The instance response should report the intended version with the `+glitch`
suffix. Also verify login, posting, media uploads, and background delivery.
HTTP health checks do not cover those authenticated operations.

For rollback, select the recorded application and streaming image digests in
[defaults](defaults/main.yml) and redeploy. An image rollback is appropriate
only when compatible with the current database schema; otherwise restore the
pre-upgrade database dump and matching application images and environment files.
Keep those recovery artifacts until the upgrade has been verified.
