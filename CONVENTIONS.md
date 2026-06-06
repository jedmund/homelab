# Conventions

How services are wired up in this repo, and how to add a new one. The goal
is that services of the same kind look the same, so a change to one reads
like a change to any other.

Every stack is a product-level Ansible role under `roles/<name>/`, deployed
by `deploy/<name>.yml` to the host group `<name>` in `inventory/hosts.yml`.
A role renders a `compose.yaml` (and any env/config files) onto the host at
`/opt/docker/<stack_name>/` and brings it up with `community.docker.docker_compose_v2`.
Companion containers that are part of one product, such as an app database,
worker, browser, search engine, or cache, stay in that product role.

## Service categories

Every service falls into one of three categories. Pick the matching
reference role and copy its shape.

### 1. Remote / third-party image

A container from a public registry (linuxserver, official upstream, a
vendor's GHCR image) that we run as-is.

Reference: **`roles/media_acquisition`**.

- Image and tag live in `defaults/main.yml` as `<svc>_image` and, where the
  tag is pinned, `<svc>_image_tag`. The compose template references the
  vars, never a hardcoded image string.
- Exposed through Traefik with **docker labels** on the container, attached
  to the `proxy` network (see Traefik section below).
- Database/internal traffic goes on the `backend` network.
- Env via an `env_file:` under `./env/<svc>.env` (rendered from
  `templates/env/<svc>.env.j2`) or an inline `environment:` block; prefer
  `env_file` when secrets are involved so they land in a `0600` file.

### 2. External / host-routed service

Something Traefik should route to that the docker provider can't see: a
service on another host, a `network_mode: host` container, or a native
(non-Docker) app on the Mac.

Reference: **`roles/infra_gateway/templates/traefik/dynamic/services-mini.yml.j2`**
(and `services-max.yml.j2` for the `max` host).

- Routed by Traefik's **file provider**, not docker labels. Add a `router`
  plus a `service` entry pointing at `http://<ip>:<port>`, where `<ip>` is
  sourced from inventory (`{{ hostvars['<host>'].ansible_host }}` or a var
  like `max_server_ip`) so the address lives in one place.
- Use this when, and only when, the docker provider cannot discover the
  container: cross-host, host networking (feederhub is the live example),
  or a native macOS service (openclaw). Anything on the `proxy` network on
  the same host as Traefik uses docker labels instead (category 1 or 3).

### 3. Self-developed app

One of our own apps (an app we maintain the source for). These are
**built by CI in the app's own repo and pulled here by tag** — this repo
does not build from source.

Reference: **`vane`** in `roles/utilities` (`defaults/main.yml:69-92`,
the `vane:` service in `templates/compose.yaml.j2`, and the registry-login
task in `tasks/main.yml`). `feederhub` is a second example.

Required `defaults/main.yml` vars (mirror `vane_*`):

```yaml
<app>_image: registry.atelier.house/jedmund/<app>   # or ghcr.io/jedmund/<app>
<app>_image_tag: <pinned-tag>                        # operator bumps to roll forward
# Registry auth (private registries only). Vault-backed, read_registry token:
<app>_registry_url: https://registry.atelier.house
<app>_registry_username: "{{ vault_<app>_registry_username | default('') }}"
<app>_registry_password: "{{ vault_<app>_registry_password | default('') }}"
```

Compose entry:

```yaml
<app>:
  container_name: <app>
  image: "{{ <app>_image }}:{{ <app>_image_tag }}"
  restart: {{ restart_policy }}
  networks:
    - proxy
  # ... env_file / environment, volumes, traefik labels, logging
```

Registry login task (private images only), before the deploy task — copy
from `roles/utilities/tasks/main.yml`:

```yaml
- name: Authenticate with <app> image registry
  community.docker.docker_login:
    registry_url: "{{ <app>_registry_url }}"
    username: "{{ <app>_registry_username }}"
    password: "{{ <app>_registry_password }}"
    reauthorize: true
  when: <app>_registry_username | length > 0 and <app>_registry_password | length > 0
  no_log: true
```

The deploy/handler tasks use `pull` (the default pull policy lives in
`group_vars/compute_servers/docker.yml`); bumping `<app>_image_tag` and
re-running the playbook is enough to roll forward. Do **not** use a
`build:` block or a git-clone task.

App-repo prerequisite: the app's own repo must have a CI job that builds
and pushes `registry.atelier.house/jedmund/<app>:<tag>` (mirror what
jedmund/Vane does). **CI credentials live in GitLab CI/CD Variables, never
in this repo's Ansible vault.**

Accepted exception: a handful of services layer a few extra packages onto
an upstream image with a small `Dockerfile` built on the host (Borgmatic in
`roles/backup`, Synapse in `roles/matrix`, catbro in `roles/petlibro`), and
`album_sort` still builds the in-house Album Sort app plus Beets helper from
a host clone. These stay build-on-host for now. New services should not
adopt this pattern without reason.

## Image tag policy

Aspirational (documented, not yet enforced across existing third-party
roles):

- Put every image and tag in `defaults/main.yml` vars, not hardcoded in the
  compose template.
- Pin tags for reproducibility. Use a floating tag (`:latest`, a release
  channel) only where automatic updates are intentional, and say so in a
  comment.

## Adding a service: checklist

1. Pick the category above and the product role it belongs in. Create a new
   product role/playbook only for a new product boundary; otherwise add the
   helper service to the existing product role that owns it.
2. Add config to that role's `defaults/main.yml`: image/tag (or registry
   vars for a self-developed app), domain, ports. Reference secrets as
   `{{ <name> }}` with a `# <name> - defined in vault` comment; never paste
   secrets or emails (this repo is public).
3. Add the service to the role's `templates/compose.yaml.j2`. Keep the
   existing header (`# {{ ansible_managed }}` then `name: {{ stack_name }}`),
   attach to `proxy` (Traefik) and/or `backend` (DB) networks, and add a
   `logging:` block matching the others.
4. Secrets: add an `env` template `templates/env/<svc>.env.j2` (header
   `# {{ ansible_managed }}` + a description), and add `<svc>` to the
   env-file loop in `tasks/main.yml`. Add the vault entries with
   `make edit-vault FILE=group_vars/<stack>/vault.yml` and document them in
   the README vault tables.
5. Expose it: docker labels for a containerized service on `proxy`
   (category 1 / 3), or a file-provider entry in `services-mini.yml.j2` /
   `services-max.yml.j2` for an external/host-routed one (category 2).
6. File modes: `0644` for compose and non-secret configs, `0600` for env
   files and any config containing secrets.
7. Handler: rely on the role's existing `Restart {{ stack_name }} stack`
   handler, which uses `state: present` + `recreate: always` (not
   `state: restarted`). `notify:` it from the template tasks.
8. Deploy and verify (`make syntax`, `make lint`, then
   `make dry-run` / `ansible-playbook --check --diff deploy/<stack>.yml`).

## Networks

- `proxy` — Traefik-facing; any service Traefik routes to via docker labels.
- `backend` — internal DB / service-to-service traffic.
- `shared` — cross-stack connectivity where needed.
- Host networking (`network_mode: host`) only when the workload needs it
  (e.g. WebRTC/ICE); such services route through the Traefik file provider.
