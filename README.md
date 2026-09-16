# Homelab

Ansible configuration for the homelab hosts, container stacks, and native
macOS services. Ansible manages deployment files and host configuration.
Komodo uses the generated Compose files for selected application deployments.

## Start here

| Task | Reference |
| --- | --- |
| Set up a checkout, deploy, or diagnose a failure | [Operations](docs/operations.md) |
| Create or update vault files | [Secrets](docs/secrets.md) |
| Add a service or change a role | [Conventions](CONVENTIONS.md) |
| Configure Komodo Resource Sync or review apps | [Komodo](komodo/README.md) |
| Check backup coverage and recovery requirements | [Backup](roles/backup/README.md) |
| Recover a deployment that predates the retired migrations | [Migration record](docs/retired-migrations.md) |

## Hosts

Assignments are defined in [inventory/hosts.yml](inventory/hosts.yml).

| Host | Managed workloads |
| --- | --- |
| `nuc-mini` | Gateway, application stacks, GitLab, Komodo Core, backups, Linux agent tooling |
| `max` | GPU inference, Linux CI runner, emulator streaming, Komodo Periphery |
| `mac-mini` | Native macOS runner, Paseo daemon, monitoring |
| `dokploy-vm` | Dokploy guest, provisioned separately through `dokploy_host` |

`mac-mini` belongs to `compute_servers` but skips Linux Docker prerequisites.
The monitoring play still includes it. Inventory membership describes desired
placement; it does not report whether a service is running.

## Common commands

Run these from the repository root after completing [setup](docs/operations.md#setup).

```sh
make check
make -C deploy list
make -C deploy check STACK=prowlarr
make -C deploy prowlarr
```

`make check` runs static checks. `make -C deploy check` connects to the target
host in Ansible check mode. A successful check-mode run is not a deployment
or an application health check.

```sh
make deploy-infra-gateway
make deploy-all-check
make deploy-all
```

The gateway command deploys Traefik, PocketID, TinyAuth, Line, OpenSpeedTest,
and ddclient in that order. The full deployment follows
[deploy/all.yml](deploy/all.yml), including prerequisites and routine stacks.
Explicit bootstrap and GPU-profile workflows are listed in
[Operations](docs/operations.md#explicit-workflows).

## Repository layout

| Path | Contents |
| --- | --- |
| [deploy/](deploy/) | Per-stack playbooks, the full deployment, and a per-stack Makefile |
| [roles/](roles/) | Defaults, tasks, templates, handlers, and service-specific runbooks |
| [inventory/hosts.yml](inventory/hosts.yml) | Hosts, connection settings, and group membership |
| [group_vars/](group_vars/) | Shared and per-group settings; local vault files are ignored by Git |
| [komodo/stacks.toml](komodo/stacks.toml) | Komodo Stack, Action, and user-group declarations |
| [requirements.yml](requirements.yml) | Ansible collection dependencies |
| [ansible.cfg](ansible.cfg) | Inventory, role path, vault password path, and connection defaults |
| [Makefile](Makefile) | Setup, validation, deployment, and maintenance commands |

`deploy/group_vars` is a symlink to `../group_vars`. It allows playbooks under
`deploy/` to load the repository's group variables.

Most container roles write to `/opt/docker/<stack_name>`. The role's defaults
and tasks define the actual path. For example, Kibble retains
`/opt/docker/feederhub`, and MusicBrainz uses an upstream checkout with a
merged Compose file.

## Service runbooks

Use `make -C deploy list` for the current playbook list. The following roles
have additional operating instructions:

| Area | Runbooks |
| --- | --- |
| Applications | [Album Sort](roles/album_sort/README.md), [Aurral](roles/aurral/README.md), [HuggingHack](roles/hugginghack/README.md), [Kaneo](roles/kaneo/README.md), [Kizuna](roles/kizuna/README.md) |
| Media | [MusicBrainz](roles/musicbrainz/README.md), [RomM](roles/romm/README.md) |
| Feeders | [Kibble](roles/kibble/README.md), [Petlibro](roles/petlibro/README.md) |
| Infrastructure | [Backup](roles/backup/README.md), [Docker boot recovery](roles/docker/NOTES.md), [Gatus](roles/gatus/README.md), [Periphery](roles/infra_periphery/README.md), [GitLab upgrades](roles/gitlab/GITLAB_UPGRADE.md) |
| GPU inference | [AI](roles/ai/README.md), [Model catalogue](roles/ai/MODELS.md), [vLLM](roles/vllm/README.md), [SGLang experiments](roles/sglang/README.md) |

Historical upgrade reports and experimental notes describe the configurations
and dates they record. Use role defaults and inventory for the current
configuration.
