# Compose lifecycle checks

Run with Python from the Ansible environment (Ansible and PyYAML must be
importable, and `ansible-playbook` must be on PATH):

```sh
python3 tests/compose_lifecycle.py --static-only
python3 tests/compose_lifecycle.py
```

The static check verifies handler references and that configuration change
results are available before each Compose apply. The integration checks load
the repository's actual build and deployment tasks with fixture variables and
files. They test container identity, applied configuration, build decisions,
failed-build retries, check mode, and removal of an optional service.

Integration checks require a local Docker Unix socket. They use a small
`alpine:3.20` image, pulling it if absent, and create UUID-named Compose projects
with no published ports or production volumes. Containers and fixture images
are removed on completion or failure. Temporary logs remain at the printed
path. The base image and Docker build cache are retained.

For a focused run:

```sh
python3 tests/compose_lifecycle.py --roles prowlarr line
```

A fresh Docker CLI configuration and Ansible configuration keep the tests
independent of repository inventory, vaults, registry credentials, and the
control machine's buildx settings. No managed homelab host is contacted.
