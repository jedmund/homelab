# Repository instructions

This repository manages live homelab hosts with Ansible. Most application
roles deploy Docker Compose stacks; host provisioning and native macOS
services have separate task layouts.

`CLAUDE.md` is a symlink to this file. Keep shared instructions here.

## Before editing

Read [README.md](README.md), [CONVENTIONS.md](CONVENTIONS.md), and the affected
role's runbook. Use [Operations](docs/operations.md) for deployment commands
and [Secrets](docs/secrets.md) for vault inputs and placement.

Inspect the working tree and preserve existing edits. Treat role defaults,
tasks, templates, and inventory as the source for configured behavior.
Historical reports describe their recorded date, not current host state.

## Repository map

- `inventory/hosts.yml`: hosts, connection settings, and deployment groups.
- `deploy/`: standalone playbooks and `all.yml`; its `group_vars` symlink
  points to the root group variables.
- `roles/<service>/`: defaults, tasks, handlers, templates, and runbooks.
- `group_vars/`: shared and per-group variables, including ignored local vaults.
- `komodo/stacks.toml`: declarations for deployments using generated files.
- `Makefile` and `deploy/Makefile`: validation and deployment entry points.

## Changes

Keep required databases, workers, and caches with their application role.
Follow the affected role's layout and the conventions for new configuration.
Preserve deployment paths, Compose project names, and volume identities
unless the task explicitly includes moving the data.

When adding or removing a service, check the inventory, standalone playbook,
`deploy/all.yml`, Make targets, DNS, Traefik, authentication, backup coverage,
Komodo declarations, and documentation. Explicit workflows excluded from the
full deployment need a `deploy-all-exclude` annotation with a reason.

Deleting deployment code does not uninstall software, delete existing DNS
records, or revoke credentials. Distinguish repository cleanup from changes
applied to hosts or external services.

Do not commit credentials, decrypted vaults, generated deployment files, or
debug output. Avoid printing secrets during inspection or validation. Use
placeholder values when checking templates locally, and retain `no_log` on
tasks that handle credentials.

## Validation and deployment

Run commands from the repository root unless using `make -C deploy`.

```sh
make check
git diff --check
```

Run these after changing Ansible, inventory, templates, or Make targets.
`make check` checks full-deployment coverage, playbook syntax, and lint.
For documentation-only changes, check local links, referenced paths, and
command names, then run `git diff --check`.

Use targeted rendering or configuration checks when syntax and lint cannot
verify the changed behavior. Do not add tests that merely repeat the source.

These commands contact managed hosts:

```sh
make -C deploy check STACK=<service>
make -C deploy <service>
```

The first runs Ansible check mode; the second applies the playbook. Check
mode can still execute tasks marked to run in that mode. Deploy within the
scope authorized by the user. A request to edit documentation or code alone
does not call for a deployment. When applying changes, verify the affected
service and report which host and checks were used.

## Documentation and handoff

Use plain, clinical language. Describe current behavior, prerequisites,
commands, expected results, and known limitations. Avoid promotional prose,
conversation history, and unsupported claims about live state. Keep detailed
service instructions in the role's runbook and link to them from shared docs.

Report what changed, what was verified, and anything left unresolved. Say
whether changes were deployed. When asked to commit, use focused Conventional
Commits and stage explicit paths. Inspect remotes before publishing; do not
assume every remote uses the same hosting service.
