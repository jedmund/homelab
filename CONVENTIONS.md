# Conventions

Use these conventions when adding or changing a service. Contributor workflow
and validation requirements are in [Contributing](CONTRIBUTING.md). Operating
commands are in [Operations](docs/operations.md).

## Role boundaries

Keep an application and its databases, workers, caches, and other required
containers in one product role. Use a separate role when a component has an
independent deployment lifecycle.

A typical container stack has:

```text
roles/<service>/
  defaults/main.yml
  tasks/main.yml
  templates/compose.yaml.j2
  templates/env/<service>.env.j2
deploy/<service>.yml
```

Most standalone playbooks use a matching inventory group. Exceptions are
explicit in the playbook: `beszel_agents.yml` applies the `beszel_agent` role,
and the vLLM and SGLang playbooks target the `ai` group. Native macOS and host
provisioning roles do not use the Compose layout.

Role defaults define stack identity and deployment paths. Preserve existing
paths and volume names when renaming a role. Moving data is a separate
operation; changing `stack_name` alone is not a migration.

## Variables and secrets

Put configurable image references, ports, domains, paths, and feature flags
in `defaults/main.yml`. Prefix new service-specific variables with the role
name. Existing container roles share `stack_name` and `config_base` by design.

Use inventory for host connection details and placement. Shared container
settings belong in [group_vars/compute_servers](group_vars/compute_servers/):

- `common.yml`: runtime user/group IDs, timezone, logging, network names;
- `docker.yml`: base path and default pull policy;
- `storage.yml`: NFS exports and external volumes;
- `ci_cache.yml`: shared runner-cache connection settings.

Store secrets in the inventory group's local encrypted `vault.yml`. Document
the exact input names, including any `vault_` prefix. Defaults may map a vault
input to a runtime variable, for example:

```yaml
app_registry_password: "{{ vault_app_registry_password | default('') }}"
```

An empty default allows parsing; it does not establish that a credential is
optional. Add assertions for required credentials before making deployment
changes. See [Secrets](docs/secrets.md) for file placement and creation.

## Images and builds

For new application roles, use images published by the application's CI.
Keep the image reference in defaults and use an immutable release or commit
tag where available. If a floating tag is intentional, document its update
trigger and rollback method in the role's README.

The shared pull policy is `always`; individual roles may override it. Image
tags and collection versions are not uniformly pinned across the existing
repository. Do not describe a deploy as version-preserving unless the
applicable image and build references are pinned.

Use [Vane](roles/vane/tasks/main.yml) as a reference for private-registry
login. Credentials used to pull an image belong in Ansible Vault. Credentials
used by CI to build or publish belong in that application's CI configuration.
Mark authentication and secret-rendering tasks `no_log: true`.

Existing host builds are supported exceptions:

| Role | Build source |
| --- | --- |
| `backup` | Borgmatic image extended with backup utilities |
| `matrix` | Custom Synapse Dockerfile |
| `petlibro` | catbro source checkout, only when enabled |
| `line` | Line source checkout |
| `hugginghack` | Fork fetched through a Compose Git build context |
| `strudel` | Repository-managed Dockerfile |
| `musicbrainz` | Upstream checkout and merged Compose configuration |

Album Sort pulls CI-built application and Beets images. It no longer builds
from a host checkout. Any new host-build exception needs a documented source
revision and rebuild policy.

## Compose files and task lifecycle

Use [Prowlarr](roles/prowlarr/) as the reference for a simple image-based
stack. Templates start with the managed-file header and explicit project name:

```yaml
# {{ ansible_managed }}
name: {{ stack_name }}
```

Use one `community.docker.docker_compose_v2` task for the normal deployment.
Compose-file changes use automatic recreation. Register results from runtime
configuration tasks and pass `recreate: always` to that same deployment when
any result changed; otherwise use `auto`. Use `changed | default(false)` for
optional and skipped inputs. A registered loop result already aggregates
changes across its items.

Do not also notify a Compose restart handler. Keep required non-Compose
handlers, such as systemd reloads or application-specific reconfiguration.
Apply configuration before deployment and run health checks and provisioning
after it. Seed application-managed configuration only when absent; preserve
existing settings when applying targeted edits.

File permissions are `0644` for public configuration and `0600` for files
containing secrets. Put secret environment variables in an environment file
when supported. Use the actual application UID/GID for writable data paths;
do not assume the shared `puid` and `pgid` apply to every image.

Use shared logging variables unless the service requires a documented
exception. Define health checks that test the service being deployed.
Mounted configuration changes need an explicit reload or restart strategy.
Preserve each role's configured pull policy. For local-build stacks, separate
runtime changes from build inputs. See [local builds](docs/operations.md#local-image-builds)
for fingerprints, retries, and explicit rebuilds. Keep any build inspection
that resolves environment variables under `no_log: true`.

## Networks and routing

Networks are created by the `networks` role. Compose aliases commonly map to:

| Alias | Docker network | Use |
| --- | --- | --- |
| `proxy` | `proxy-network` | Traefik and routed containers on the same Docker host |
| `backend` | `backend-internal` | Database and internal service traffic; external egress is disabled |
| `shared` | `shared-network` | Cross-stack traffic and services that need egress |
| `cibuild` | `cibuild-network` | GitLab CI jobs and their supporting services |
| Service-specific | `vpn-network` | VPN-related connectivity |

Docker bridge networks are local to each host. Reusing a name on `max` does
not connect it to the network on `nuc-mini`.

For containers on Traefik's host and proxy network, declare routers and
services with Docker labels. For other hosts, native services, and
host-network containers, use the Traefik file provider:

- [services-mini.yml.j2](roles/traefik/templates/traefik/dynamic/services-mini.yml.j2)
- [services-max.yml.j2](roles/traefik/templates/traefik/dynamic/services-max.yml.j2)
- [services-other.yml.j2](roles/traefik/templates/traefik/dynamic/services-other.yml.j2)

Derive managed-host addresses from inventory. Specify the route's TLS and
authentication behavior. Use PocketID for native OIDC where supported;
TinyAuth middleware and its per-application access labels cover selected
other routes. Do not infer authentication from network membership.

## Add a service

1. Choose the role boundary and target inventory group. Keep required helper
   containers in the owning product role.
2. Define defaults, templates, data paths, credentials, and deployment tasks.
3. Add the standalone playbook. Import routine playbooks in
   [deploy/all.yml](deploy/all.yml). For an explicit bootstrap, experimental,
   or mode-switch workflow, add a `deploy-all-exclude` annotation with a reason.
4. Add DNS, Traefik routing, authentication, and firewall configuration as
   required. Deploy PocketID and TinyAuth before dependent applications.
5. Add backup coverage for databases, bind mounts, and named volumes. Record
   NFS data that needs a separate NAS backup.
6. If Komodo manages the stack, add its declaration to
   [komodo/stacks.toml](komodo/stacks.toml) using the actual host path.
7. Document first-deploy steps and verification in the role's README. Add a
   link from the root README if the role has a runbook. Do not duplicate a full
   service roster or variable list in multiple guides.
8. Run `make check`, review a targeted check-mode run where supported, deploy,
   and verify the service's health and authentication behavior.

When a migration is complete on every assigned host, remove its one-time code
and document the historical implementation and recovery requirements in
[retired migrations](docs/retired-migrations.md). Retain guards for migrations
that have not completed.
