# Compose lifecycle checks

Run with Python from the Ansible environment. Ansible and PyYAML must be
importable, `ansible-playbook` must be on PATH, and the Docker CLI must include
the Compose plugin:

```sh
python3 tests/test_maintenance.py
python3 tests/compose_lifecycle.py --static-only
python3 tests/compose_lifecycle.py
```

The static phase verifies handler references, configuration-change decisions,
and rendered production Compose files. The lifecycle phase loads the repository's
actual build and deployment tasks with fixture variables and files. It tests
container identity, applied configuration, build decisions, failed-build retries,
check mode, and removal of an optional service.

The maintenance tests cover the staging allowlist, BentoPDF image/health and
Procedure contracts, backup freshness and required artifacts, NFS archive
divergence, Prowlarr SQLite integrity failure, and temporary-file cleanup.

Integration checks require a local Docker Unix socket. They use a small
`alpine:3.20` image, pulling it if absent, and create UUID-named Compose projects
with no published ports or production volumes. Containers and fixture images
are removed on completion or failure. Temporary logs remain at the printed
path. The base image and Docker build cache are retained.

For a focused run:

```sh
python3 tests/compose_lifecycle.py --lifecycle-only --roles prowlarr line
```

A fresh Docker CLI configuration and Ansible configuration keep the tests
independent of repository inventory, vaults, registry credentials, and the
control machine's buildx settings. No managed homelab host is contacted.

## Fast validation

Run the checks that do not need Ansible or Docker with:

```sh
python3 tests/test_validation.py
python3 ci/validation.py fast
```

The fast command validates links and anchors in tracked Markdown, parses and
checks the structure of `komodo/stacks.toml`, and runs `git diff --check`.
`ci/validation.py plan` compares the branch with a supplied review base. It
selects fast checks for documentation and Komodo declarations, static checks
and affected lifecycle fixtures for covered roles, and the full suite for shared,
unknown, or uncovered inputs. Missing history and empty comparisons select the
full suite.

## Isolated validation

`bash ci/run` builds the validation image and runs the full suite. Pass `static`
or `lifecycle` and optional role names to run one phase. Tool and collection
versions are pinned in `ci/requirements.txt` and `ci/collections.yml`; update
these together after testing a tooling upgrade.

The launcher requires a Linux Docker daemon that can start privileged
containers. Each run starts a temporary container with its own Docker daemon.
The runner's Docker socket, host directories, and credentials are not mounted
inside it. `ci/Dockerfile.dockerignore` excludes vaults and local scratch files
from the image. CI uses `ci/ansible.cfg`, which has no vault-password setting.

The launcher removes its container, anonymous volumes, and image tag on exit.
Docker's build cache remains on the runner. Logs and JSON timing reports are
copied to `ci-results/`, which is ignored by Git. CI retains them for seven days.

GitHub runs fast validation automatically for pull requests. It does not run on
pushes to `main`. Manual dispatch offers fast or full validation; the full option
uses Actions minutes and runs the isolated suite serially.

GitLab runs merge-request and branch pipelines, suppressing duplicate push
pipelines when a merge request is open. A planning job always runs fast checks.
Selected static validation and a fixed four-job lifecycle matrix then run in
parallel, followed by one aggregate result. Scheduled pipelines and pipelines
with `CI_SUITE=full` select every phase. The Docker jobs use the existing
`docker` and `atelier-max` runner tags and their mounted Docker sockets to launch
isolated containers. A replacement runner must provide the same capability or
the job tags must be updated. Neither pipeline deploys homelab services.

## Minecraft

`python3 tests/test_minecraft.py` and `python3 tests/test_minecraft_transfer.py`
exercise stopped snapshots, deferral, concurrent wake, copy timeout, router
recovery, missing data, stale/corrupt transfers and unavailable NAS storage.
Use Python with Jinja2 and PyYAML installed.

`tests/test_minecraft_lifecycle.py` uses disposable Compose projects against
`DOCKER_HOST`; it tests sleeping/mixed state and container identity.
`tests/test_minecraft_routing.py <ssh-host>` uses the pinned router and proxy
with disposable backends and a loopback-only ephemeral port on that host.
Set `DOCKER_HOST=ssh://<ssh-host>` for the same host. It verifies status-only
polling, selected wake, loading messages and unknown-host rejection. Both
fixtures clean up their containers and networks and never mount production data.

`DOCKER_HOST=ssh://nuc python3 tests/test_minecraft_lock.py borgmatic`
checks the production Borg wrapper against the container's actual `flock`,
using only a temporary directory and a fake Borg command. It verifies that
publication and readers exclude each other and release locks.
