# Repository guidance

This repository manages the homelab with Ansible. Read `CONVENTIONS.md`
before changing a service role, deployment playbook, container image, network,
or secret-handling path.

## Working agreements

- Keep each product in `roles/<name>/` with a matching `deploy/<name>.yml`
  playbook and inventory group.
- Preserve unrelated work in the checkout. Do not modify ignored vault files
  or local overrides unless the user explicitly asks.
- Never commit credentials. Render secrets into host files with mode `0600`
  and use `no_log: true` on Ansible tasks that expose secret values.
- Prefer idempotent Ansible modules over shell commands. When a command is
  necessary, give it accurate `changed_when`, `failed_when`, or `creates`
  behavior.
- Follow the image, networking, handler, and file-layout conventions in
  `CONVENTIONS.md`.
- Keep operational migrations and retired-resource cleanup explicit. Remove
  them only after confirming every affected host has converged.

## Validation

Run the complete static validation suite after repository changes:

```bash
make check
```

`make check` runs syntax checks for every playbook and then `ansible-lint`.
It is non-interactive and does not require a vault password when the local
password file is absent. Use `make syntax` or `make lint` while iterating.

Deployment and dry-run targets connect to homelab hosts and may require vault
access. Do not run them unless the task calls for deployment or live-host
verification.

## Dependency maintenance

`requirements.yml` contains Ansible Galaxy collections, not roles. Install
them with `make setup` and upgrade them with:

```bash
make update-collections
```

Use a focused branch and keep dependency changes separate from unrelated
service changes.
