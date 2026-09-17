# Working on Homelab

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing this repository. It owns
the contributor workflow, validation requirements, and publishing rules. Read
[README.md](README.md), [CONVENTIONS.md](CONVENTIONS.md), and the affected role's
runbook. Use [Operations](docs/operations.md) for deployment commands and
[Secrets](docs/secrets.md) for vault placement and inputs.

`CLAUDE.md` is a symlink to this file. Keep shared agent instructions here.

## Work within the existing structure

- Survey the working tree and preserve unrelated edits and local secrets.
- Inspect defaults, tasks, templates, inventory, and tests before changing
  behavior. Historical reports are not evidence of current host state.
- Keep applications and their required databases, workers, and caches in the
  owning role. Follow Conventions for the single Compose deployment lifecycle.
- Preserve deployment paths, project names, volume identities, and persistent
  keys unless the task includes migrating them.
- Check all service registrations when adding or removing a service. Retire
  migration code only after verifying completion on its assigned hosts.
- Use placeholder values for local rendering. Preserve `no_log`; never print
  credentials or commit vaults, generated deployment files, or debug output.
- Check existing vault locations before replacing a missing worktree credential.
  Do not generate new persistent keys to bypass a failed deployment.

## Validate and report

Follow [Contributing: Validation](CONTRIBUTING.md#validation). Ansible, inventory,
template, and Make changes require `make check` and `git diff --check`, plus
focused checks for behavior that syntax and lint cannot establish. Documentation
changes need link, path, command, and diff checks. Do not weaken a gate or hide a
failure to pass validation.

Deploy only within the user's authorized scope. Check mode contacts managed
hosts and may execute tasks. An edit or PR request alone does not authorize a
deployment. Verify service health and affected behavior after deploying; report
which host and checks were used and what remains untested.

When asked to commit or publish, follow
[Contributing: Commits and pull requests](CONTRIBUTING.md#commits-and-pull-requests).
Print the exact-path commit plan before staging, use focused Conventional Commits,
inspect each commit, and check the remote before selecting `gh` or `glab`.
Never bypass hooks or signing. Opening a PR does not authorize merging it.

Use plain, clinical documentation. Report what changed, what passed or failed,
whether it was deployed, and anything unresolved. Keep service procedures in
role runbooks and link to them from shared documentation.
