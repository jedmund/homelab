# GitLab

This role deploys GitLab CE, the `nuc-mini-docker` runner, Renovate, and a
dedicated single-node Garage instance for shared CI cache. The
`development_linux` role runs the second Docker runner on `max`.

## Vault

`group_vars/gitlab/vault.yml` defines:

```yaml
gitlab_initial_root_password: <initial-password>
gitlab_oidc_client_id: <pocketid-client-id>
gitlab_oidc_client_secret: <pocketid-client-secret>
gitlab_runner_auth_token: <nuc-mini-runner-token>
gitlab_cache_garage_rpc_secret: <garage-rpc-secret>
gitlab_cache_garage_admin_token: <garage-admin-token>
renovate_gitlab_token: <renovate-personal-access-token>
renovate_github_token: <optional-github-token>
```

The cache credentials shared by both runners live in
`group_vars/compute_servers/vault.yml`:

```yaml
gitlab_cache_s3_access_key_id: <garage-access-key>
gitlab_cache_s3_secret_access_key: <garage-secret-key>
```

## CI cache bootstrap

After the first `make deploy-gitlab`, run the idempotent helper on `nuc-mini`:

```sh
ssh nuc-mini
cd /opt/docker/gitlab
./ci_cache_bootstrap.sh
```

The first run assigns the Garage layout, creates the `ci-cache` bucket, and
prints an S3 key. Put that key pair in the shared `compute_servers` vault,
then deploy GitLab again. The role imports the credentials, grants bucket
access, and applies the object-expiry lifecycle.

Until the shared S3 keys are populated, each runner falls back to its local
cache. Cache objects expire after `gitlab_cache_s3_expiry_days` (14 days by
default).

## Upgrades and recovery

GitLab upgrades must follow required intermediate versions and wait for
background migrations. Use [GITLAB_UPGRADE.md](GITLAB_UPGRADE.md), which also
documents backups, runner draining, validation, and version-specific recovery
points.
