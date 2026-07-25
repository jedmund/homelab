# Komodo Resource Sync

`stacks.toml` declares the Komodo resources owned by this repo: Stack resources
for Ansible-rendered Docker Compose projects and the Action used by Kizuna's
Storybook Review Apps.

## Operating model

- Ansible writes `/opt/docker/<stack>/compose.yaml` and any env/config files.
- Komodo uses `files_on_host = true` and only points at those rendered files.
- Komodo should not clone stack repos, edit stack files, poll for image updates,
  or auto-update stacks behind Ansible.
- CI-triggered stacks keep their existing resource names:
  `kibble`, `vane`, and `kizuna`.
- The `kizuna-storybook-review` Action is the exception to the static-stack
  model: it creates ephemeral, MR-scoped Stack resources from a constrained
  image and host pattern, then removes them when GitLab stops the environment.

## Sync setup

Create a Komodo Resource Sync that points at this file:

```toml
resource_path = ["komodo/stacks.toml"]
```

Use match tag `homelab` if you want this sync to own only the resources in
this file. Apply the first sync from the UI after reviewing the diff.

Expected Komodo Server resource names:

- `Atelier` for `nuc-mini`
- `max` for the GPU host

If the live Komodo Server resource for `max` uses a different name, update the
max-host stack declarations in `stacks.toml` before applying the sync.

## Kizuna Storybook reviews

The `kizuna-storybook-review` Action accepts only the merge-request operation,
IID, image, host, and revision supplied by `kizuna-app` CI. It hard-codes the
operational boundary:

- server: `Atelier`;
- images: immutable Storybook tags below
  `registry.atelier.house/kizuna/kizuna-app/storybook`;
- hosts: `storybook-mr-<iid>.review.atelier.house`;
- network: `proxy-network`;
- authentication: Traefik's `tinyauth@file` middleware, backed by PocketID;
- TLS: the `letsencrypt` resolver.

The Kizuna Ansible role already logs the host in to
`registry.atelier.house` with its read-only deploy token. Keep that credential
current because the ephemeral stacks deliberately do not contain registry
secrets.

Before enabling the app CI jobs:

1. Deploy `infra_gateway` so Cloudflare has
   `*.review.atelier.house` and Traefik has the nested wildcard certificate.
2. Apply this Resource Sync and grant the Kizuna CI service user execute-only
   access to `kizuna-storybook-review`.
3. In `kizuna-app`, set `STORYBOOK_REVIEW_DOMAIN=review.atelier.house` and
   `KOMODO_STORYBOOK_REVIEW_ACTION=kizuna-storybook-review`, alongside the
   existing Komodo API credentials.

GitLab owns expiry and stop events. A deploy updates the deterministic
`kizuna-storybook-mr-<iid>` Stack; a stop destroys its containers and deletes
the Stack resource. The Storybook container has no host port and is reachable
only through the authenticated TLS router.

## Legacy resources

After the split stacks are healthy, remove the old thematic Stack resources
from Komodo:

- `media-acquisition`
- `media-consumption`
- `content-management`
- `reading`
- `productivity`
- `utilities`
- `development`

Do not delete Docker volumes or runtime directories from Komodo. The Ansible
migration and archive playbooks own data movement and rollback state.

## Special cases

- `musicbrainz` points at `/opt/docker/musicbrainz/upstream` and
  `local/compose.merged.yml`, matching the role's generated merged compose.
- `beszel-agent-max` and `beszel-agent-nuc-mini` point at the same
  `/opt/docker/beszel-agent` run directory on different Komodo server
  resources. The `mac-mini` agent is native Homebrew, so it has no Komodo
  Stack resource.
- `vllm` and `sglang` are profile-gated stacks. Komodo can track their compose
  files, but model lifecycle remains an explicit operator action.
