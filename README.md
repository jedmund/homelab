# Homelab

Ansible playbooks for deploying and managing the Atelier homelab.

## Documentation

Start here, then follow the guide that owns the detail you need:

| Guide | Purpose |
| --- | --- |
| [Service catalog](docs/services.md) | Every role, what it manages, and links to service runbooks |
| [Vault variables](docs/vault.md) | Creating vaults and finding the secrets required by each stack |
| [Database backups](docs/database-backups.md) | Manual PostgreSQL and MariaDB backup, restore, and migration |
| [Service conventions](CONVENTIONS.md) | Repository patterns and the checklist for adding a service |
| [Komodo Resource Sync](komodo/README.md) | Applying the Komodo stack declarations |

Operational instructions that apply to only one service live beside that role
in `roles/<role>/README.md`. This keeps the root guide focused on repository
setup and common commands.

## Repository layout

```text
.
├── deploy/        # One playbook per stack; deploy/all.yml is the aggregate
│   └── group_vars -> ../group_vars
├── docs/          # Repository-wide operator guides
├── group_vars/    # Shared variables and encrypted vault files
├── inventory/     # Hosts and stack group assignments
├── komodo/        # Komodo Resource Sync declarations
├── roles/         # One role per stack or host capability
├── CONVENTIONS.md # Service design and contribution conventions
└── Makefile       # Deployment and maintenance entry points
```

The `deploy/group_vars` symlink is intentional. Ansible resolves
`group_vars/` relative to the playbook location, so playbooks under `deploy/`
need the link to read the repository's shared variables.

Most product roles have a matching `deploy/<role>.yml` playbook and inventory
group. Base roles such as `docker`, `networks`, and `firewall` are composed by
`deploy/prerequisites.yml`. See the [service catalog](docs/services.md) for the
complete mapping.

## Prerequisites

- Ansible Core 2.15+
- Python 3 on target hosts
- SSH access to target hosts

## Initial setup

1. Clone the repository.
2. Create the local Ansible configuration and vault password file:

   ```sh
   make setup
   ```

3. Update `inventory/hosts.yml` with the target hosts and stack groups.
4. Create the encrypted files described in [Vault variables](docs/vault.md).
5. Confirm connectivity:

   ```sh
   make test-connection
   ```

Each inventory host needs `ansible_host` and `ansible_user`.
`ansible_port` is optional when SSH uses port 22, and
`ansible_connection: local` can be used for the current machine.

```yaml
compute_servers:
  hosts:
    my-server:
      ansible_host: 192.168.1.100
      ansible_user: myuser

romm:
  hosts:
    my-server:
```

A host can belong to multiple stack groups.

## Common operations

Run `make help` for the authoritative list of targets.

```sh
# Validate the repository
make check

# Preview the aggregate playbook
make deploy-all-check

# Deploy the aggregate playbook
make deploy-all

# Deploy one stack
make deploy-infra-gateway
make deploy-gitlab

# Target or filter an aggregate deployment
make deploy-limit HOST=mini
make deploy-tags TAGS=traefik,plex
make deploy-skip-tags TAGS=backup
```

`make deploy-all` follows the imports in `deploy/all.yml`. Some roles have
specialized targets or one-time setup documented in the
[service catalog](docs/services.md) and their role README.

### Vault management

```sh
make edit-vault FILE=group_vars/infra_core/vault.yml
make view-vault FILE=group_vars/infra_core/vault.yml
make encrypt FILE=group_vars/new_stack/vault.yml
make decrypt FILE=group_vars/infra_core/vault.yml
```

### Inspection and maintenance

```sh
make list-hosts
make list-tags
make show-vars HOST=mini

make docker-ps
make docker-logs HOST=mini CONTAINER=traefik
make docker-prune
```

Before adding or restructuring a service, read
[CONVENTIONS.md](CONVENTIONS.md).
