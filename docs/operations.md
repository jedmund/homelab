# Operations

Run commands from the repository root unless a different location is stated.

## Setup

The control machine needs Ansible, `ansible-lint`, Git, and SSH access to the
managed hosts. Install the tools before running `make setup`; that target
installs collections, not Ansible itself. Collection versions are currently
unconstrained in [requirements.yml](../requirements.yml).

1. Review [inventory/hosts.yml](../inventory/hosts.yml), including SSH users
   and nonstandard ports. Linux host tasks use privilege escalation.
2. Run `make setup`. It creates `~/.ansible-vault-pass` if missing and installs
   collections under `~/.ansible/collections`.
3. Obtain the existing encrypted vault files and matching password for an
   existing deployment. For a new service, follow [Secrets](secrets.md).
   Vault files are not included in a clone.
4. Run `make check` for static validation, then `make test-connection` to test
   inventory connections.

The repository configuration disables SSH host-key checking. Both Makefiles
export the repository's Ansible configuration and put temporary files under
`.ansible/tmp`. Direct Ansible commands should run from the repository root.

## Validate a change

```sh
make check
```

This runs:

| Check | What it verifies |
| --- | --- |
| `make check-deploy-all` | Every standalone playbook is imported or explicitly excluded in `deploy/all.yml` |
| `make syntax` | Ansible can parse every deployment playbook and resolve its roles |
| `make lint` | Repository lint rules in `.ansible-lint` and `.yamllint` |

These checks do not connect to hosts, render every template with production
values, or verify application health. Installed collections are required;
vault handling depends on which local vault files are present.

For a targeted check-mode run:

```sh
make -C deploy check STACK=prowlarr
```

Check mode uses the target host and vault values. Some commands, lookups, and
application checks are not simulated. Review the role before relying on its
check-mode result. Diff output may contain rendered configuration; keep it
out of public logs when it includes secrets.

## Deploy one stack

```sh
make -C deploy list
make -C deploy syntax STACK=prowlarr
make -C deploy prowlarr
```

The parameterized form accepts additional Ansible arguments:

```sh
make -C deploy deploy STACK=prowlarr EXTRA_ARGS='--limit nuc-mini'
```

Use the playbook name as `STACK`, including underscores where present. Root
Makefile shortcuts are listed by `make help`; not every playbook has a root
shortcut.

After deployment, check the application's health, logs, route, and login
flow. For a standard Compose stack, run on its host:

```sh
cd /opt/docker/prowlarr
docker compose ps
docker compose logs --tail=100
```

Use the role's configured path for stacks with a different layout.

## Deploy multiple stacks

```sh
make deploy-infra-gateway
make deploy-all-check
make deploy-all
```

`deploy-infra-gateway` runs the six gateway playbooks in order: Traefik,
PocketID, TinyAuth, Line, OpenSpeedTest, ddclient. It stops if one fails.

`deploy-all` follows the imports in [deploy/all.yml](../deploy/all.yml).
Prerequisites run first. The Linux prerequisites play skips `mac-mini`; the
separate Netdata play includes all compute hosts. Backup is deployed last.
Deploying the backup stack does not itself create a backup archive.

For a subset of the full deployment:

```sh
make deploy-limit HOST=nuc-mini
make deploy-tags TAGS=traefik,plex
make deploy-skip-tags TAGS=backup
```

The prerequisites import is tagged `always`, so tag selection on `all.yml`
still includes prerequisites. Use a standalone playbook to limit a change
to one role. `make list-tags` and `make list-tasks` show the available scope.

`make deploy-monitoring` deploys Beszel. The standalone
`deploy/monitoring.yml` playbook deploys Netdata.

## Explicit workflows

These playbooks are excluded from the routine full deployment:

| Playbook | Use |
| --- | --- |
| `dokploy_host.yml` | Provision host networking and the Dokploy VM |
| `dokploy.yml` | Bootstrap Dokploy in the guest |
| `ai_split.yml` | Apply the AI configuration and start the selected vLLM profile; use `make deploy-ai-split` to pass split mode |
| `vllm.yml` | Render the profile-gated vLLM stack without starting a model |
| `sglang.yml` | Configure the parked experimental stack |
| `gpu_tools.yml` | Apply GPU tools separately; `ai.yml` already includes them |
| `monitoring.yml` | Apply Netdata separately; `prerequisites.yml` already includes it |

`make deploy-ai-shared` changes GPU allocation and stops the split inference
stacks. See [vLLM](../roles/vllm/README.md) before switching profiles. Routine
`ai.yml` deployment still applies the configured `ai_gpu_mode`; the default
is defined in the AI role.

## Images and configuration

The shared `docker_pull_policy` is `always`. Redeploying a floating tag can
therefore install a newer image without a repository change. Some roles have
an explicit pull or build policy; Album Sort, for example, always pulls.

To request cached images for a role that uses the shared setting:

```sh
make -C deploy deploy STACK=prowlarr EXTRA_ARGS='-e docker_pull_policy=missing'
```

This is not a version pin. For reproducible deployment or rollback, use an
available immutable image tag in the role's configuration and confirm that
it is compatible with the stored data. An image rollback does not reverse a
database migration.

Edit repository templates or variables, then redeploy. Ansible overwrites
manual edits to generated Compose, environment, and configuration files.
[Komodo](../komodo/README.md) uses those same files; application CI may trigger
redeployment without rerunning Ansible.

### Local image builds

Line, Backup, Matrix, MusicBrainz, Strudel, and Petlibro's optional catbro
inspect their local images and effective build inputs before deployment.
Ansible builds when an image is missing, build inputs differ from the last
successful deployment, or the role's force-rebuild variable is true. Runtime
configuration changes can recreate the stack without rebuilding its images.

The roles store a fingerprint in `.ansible-build-inputs.json` in the Compose
project directory. It contains a hash, not configuration or credentials.
The first deployment without a record rebuilds once. The record is updated
only after a successful Compose apply, so a failed build or deployment remains
eligible for retry. Check mode does not build or update the record.

| Role | Explicit rebuild variable |
| --- | --- |
| Line | `line_force_rebuild` |
| Backup | `backup_force_rebuild` |
| Matrix | `matrix_force_rebuild` |
| MusicBrainz | `musicbrainz_force_rebuild` |
| Strudel | `strudel_force_rebuild` |
| Petlibro | `petlibro_force_rebuild` (only while catbro is enabled) |

For example:

```sh
make -C deploy deploy STACK=line EXTRA_ARGS='-e line_force_rebuild=true'
```

This requests a cached build. It does not disable the build cache or force
new base images to be downloaded. Changes to upstream branches fetched inside
a Dockerfile are not tracked by Ansible; use an explicit source/image update
procedure when refreshing those dependencies.

The build fingerprints cover rendered build settings, Dockerfiles, ignore
files, and source checkout revisions where present. Hand edits to other files
in host build directories are not a supported source-update mechanism.

Ansible explicitly controls building on its own deployments. Direct Compose
and Komodo deployments still follow the rendered service policies. In
particular, `pull_policy: build` requests a build even if an image exists.
HuggingHack retains its separate database-first startup and application build.

## Backups and maintenance

[Backup](../roles/backup/README.md) defines the configured sources, database
hooks, exclusions, and recovery limits. Check coverage when adding storage or
changing a database name. NFS object data and ignored vault files require
separate backup arrangements.

`make update-collections` upgrades the installed Ansible collections. It does
not pin versions in the repository. Run validation after changing tools or
collections.

The root Makefile includes fleet-wide Docker restart, stop, and prune commands.
Inspect their recipes before use; they target all inventory hosts rather than
one Compose stack. `make clean` removes local caches and retry files.

## Diagnose a failure

| Symptom | Check |
| --- | --- |
| Role not found | Use the root checkout or `make -C deploy`; confirm `ANSIBLE_CONFIG` points to this repository |
| Undefined variable or vault error | Group membership, vault location, password file, and the role's defaults/templates |
| Missing external network or volume | Prerequisites deployment and NFS export access |
| Container runs but route fails | Traefik labels or dynamic config, network membership, DNS, and authentication settings |
| Configuration reverts after deployment | Change the source template or variable rather than the generated host file |
| Old backup or host cannot use a current role | Read the [retired migration record](retired-migrations.md) before restoring old state |
