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

## Continuous integration

GitHub Actions and GitLab CI both run `bash ci/run`. It builds the validation
image, runs `make check`, checks handler references, and executes all lifecycle
fixtures. Tool and collection versions are pinned in `ci/requirements.txt` and
`ci/collections.yml`; update these together after testing a tooling upgrade.

The launcher requires a Linux Docker daemon that can start privileged
containers. Each run starts a temporary container with its own Docker daemon.
The runner's Docker socket, host directories, and credentials are not mounted
inside it. `ci/Dockerfile.dockerignore` excludes vaults and local scratch files
from the image. CI uses `ci/ansible.cfg`, which has no vault-password setting.

The launcher removes its container, anonymous volumes, and image tag on exit.
Build cache remains on the runner. Logs are copied to `ci-results/`, which is
ignored by Git. Both platforms retain failure logs for seven days.

GitHub runs validation for pull requests, pushes to `main`, and manual runs.
GitLab runs merge-request and branch pipelines, suppressing duplicate push
pipelines when a merge request is open. The GitLab job uses the existing
`docker` and `atelier-max` runner tags and its mounted Docker socket to launch
the isolated container. A replacement runner must provide the same capability
or the job tags must be updated. Neither pipeline deploys homelab services.
