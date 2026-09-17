# Contributing to Homelab

This repository manages live hosts with Ansible. Most application roles deploy
Docker Compose stacks; host provisioning and native macOS services have separate
layouts. Start with [setup](docs/operations.md#setup) for Ansible, collections,
SSH access, and local vault placement. A clone does not include deployment secrets.

## Find the owner before changing behavior

Read the affected role's defaults, tasks, templates, inventory group, and runbook.
Use implementation to establish configured behavior and host checks to establish
live state. Historical reports describe their recorded date.

| Question | Source |
| --- | --- |
| Where is a service configured to run? | [Inventory](inventory/hosts.yml), group variables, and its standalone playbook |
| What does a role deploy? | `roles/<service>/defaults`, `tasks`, and `templates` |
| How should a role be structured? | [Conventions](CONVENTIONS.md) |
| How do I deploy or recover a service? | [Operations](docs/operations.md) and the role's runbook |
| Which secret inputs are required? | [Secrets](docs/secrets.md), role assertions, and templates |
| How are changes validated? | [Makefile](Makefile), [deployment Makefile](deploy/Makefile), and [test guide](tests/README.md) |
| How does Komodo use generated deployments? | [Komodo](komodo/README.md) and [stack declarations](komodo/stacks.toml) |

Update the owning document when changing its contract. Keep detailed service
procedures in the role's runbook and link them from the root README. Use plain,
clinical language: prerequisites, commands, expected results, and limitations.

## Make focused changes

Inspect the working tree before editing and preserve unrelated changes. Find the
existing role, task, variable, or test fixture before introducing another owner.
Follow [Conventions](CONVENTIONS.md) for role boundaries, Compose lifecycle,
networking, images, and service registration.

Keep required databases, workers, and caches with their application role.
Preserve deployment paths, Compose project names, volume identities, host
assignments, and persistent keys unless the requested change includes migrating
them. A rename can create empty storage rather than move existing data.

Name tasks for their action and variables for their meaning. Prefer explicit
conditions and module parameters over shell commands or indirect variable
construction. Use shell only when shell behavior is required. Keep configuration,
deployment, and health verification in their intended order. Avoid speculative
shared roles and helpers that only hide a small expression.

Assert required inputs before writing deployment files. Give optional and skipped
registered results safe defaults. Preserve `changed_when`, failure handling,
check-mode behavior, and the single Compose deployment path when refactoring.
Do not suppress errors, weaken lint rules, or add broad exclusions to pass checks.
Follow the repository's [.ansible-lint](.ansible-lint) and [.yamllint](.yamllint)
configuration rather than importing another project's formatting rules.

For template changes, inspect rendered output with placeholder values. Include
empty and populated lists, conditional sections, and newline boundaries when
relevant. Valid YAML or Jinja syntax does not establish that the generated
Compose, environment, or application configuration is usable.

When adding or removing a service, check inventory, standalone and full playbooks,
Make targets, DNS, Traefik, authentication, backups, Komodo, and documentation.
Full-deployment exclusions need a `deploy-all-exclude` annotation with a reason.
Remove migration tasks only after confirming completion on every assigned host.
Deleting code does not uninstall software, remove DNS records, or revoke keys.

## Secrets and local state

Keep credentials in ignored, encrypted vaults as described in [Secrets](docs/secrets.md).
Never commit credentials, decrypted vaults, generated deployment files, or debug
output. Retain `no_log` on credential handling and avoid printing secrets during
inspection, rendering, diff review, or validation.

Check the main checkout and existing local vault locations before treating a
missing worktree vault as a missing credential. Preserve existing production
values; do not generate replacements for persistent encryption keys to make a
deployment pass. Keep test data and logs outside tracked paths. Use disposable
fixtures rather than production volumes or application databases for tests.

## Validation

Run commands from the repository root unless using `make -C deploy`. The scripts
and Makefiles define the available commands; CI tool versions are pinned in
[ci/requirements.txt](ci/requirements.txt) and [ci/collections.yml](ci/collections.yml).
Normal collection setup uses [requirements.yml](requirements.yml).

| Command | Purpose |
| --- | --- |
| `make check` | Full-deployment coverage, playbook syntax, and lint; no managed-host contact |
| `git diff --check` | Whitespace errors in the working diff |
| `python3 tests/compose_lifecycle.py --static-only` | Compose lifecycle structure checks |
| `python3 tests/compose_lifecycle.py --roles prowlarr line` | Focused lifecycle fixtures using local Docker |
| `bash ci/run` | Full validation in an isolated Docker environment |
| `make -C deploy check STACK=<service>` | Ansible check mode against managed hosts |
| `make -C deploy <service>` | Apply a deployment to managed hosts |

Run `make check` and `git diff --check` after changes to Ansible, inventory,
templates, or Make targets. Add targeted rendering or configuration checks when
syntax and lint cannot verify behavior. For Compose lifecycle changes, run the
relevant fixtures; see [test prerequisites and isolation](tests/README.md).
Documentation-only changes need local-link, referenced-path, and command checks,
then `git diff --check`.

Tests should establish observable behavior: applied configuration, container
identity, rebuild decisions, failure recovery, or application readiness. Do not
add tests that merely repeat implementation details. Run focused checks during
development; repeat full suites only after relevant changes or to investigate a
failure. Both CI platforms run the shared validation launcher and do not deploy.

## Deployment

Deploy only within the user's authorized scope. An edit or PR request alone does
not authorize a deployment. Check mode contacts hosts and may execute tasks marked
to run in that mode. Review the role before relying on it as a simulation.

Before an image upgrade, read upstream release and migration notes, verify image
availability, and establish the required backup and recovery procedure. Floating
tags may update software during deployment. Keep application upgrades separate
from database-engine upgrades unless both are required by the requested change.

After applying a change, check application health and the affected behavior.
Container creation alone does not establish readiness. Verify repeat deployments
when changing restart or build decisions. Report the host, checks performed,
results, and any authenticated workflows or external integrations not tested.

## Commits and pull requests

When asked to publish, inspect remotes and use the requested destination. Use `gh`
for GitHub PRs and `glab` for GitLab MRs. Do not assume that `origin` and another
remote use the same host or that opening a PR authorizes merging it.

1. Survey `git status`, `git diff`, `git diff --staged`, and the last five commits.
   Record the starting branch and intended review base.
2. Print a plan before staging: exact paths, Conventional Commits subjects, and
   why each commit stands alone. Split independent fixes, refactors, dependency
   updates, formatting, and documentation. Keep inseparable runtime changes
   together and explain the dependency.
3. Stage explicit paths. Use `git add -p` for mixed concerns; never bulk-stage
   unrelated work or use `git commit -a`.
4. Explain the reason in each commit body. Do not add model attribution or
   co-authors. Never bypass hooks or signing. Stop on a hook failure and report
   its output verbatim.
5. Run `git show --stat HEAD` after every commit. Stop if it includes unplanned
   files or more than ten files; review the split before continuing.
6. Use one PR for one reviewable change. For independent units, plan a branch
   stack and validate each branch tip. Target the first at the agreed base and
   subsequent PRs at the preceding branch. Identify dependencies in descriptions.
7. Push and open the PR with the problem, resulting behavior, validation, and
   deployment status. Stop on a push rejection. Never force-push the base or a
   branch not created for the current work.

If an earlier PR changes, fetch and inspect before restacking. Use
`git rebase --update-refs <base>` and verify all branch refs and commits afterward.
For an intentional restack of branches created for the current work, push them
with `--force-with-lease --atomic`; never fetch immediately before that push or
use `--force`. Stop if a commit disappears, duplicates, or a lease is rejected.

Report commit summaries, PR URLs, validation, deployment status, and any unrelated
files left uncommitted. Merging and deployment remain separate authorized actions.
