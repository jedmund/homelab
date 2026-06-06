# Komodo Resource Sync

`stacks.toml` declares the Komodo Stack resources for the Ansible-rendered
Docker Compose stacks in this repo.

## Operating model

- Ansible writes `/opt/docker/<stack>/compose.yaml` and any env/config files.
- Komodo uses `files_on_host = true` and only points at those rendered files.
- Komodo should not clone stack repos, edit stack files, poll for image updates,
  or auto-update stacks behind Ansible.
- CI-triggered stacks keep their existing resource names:
  `feederhub`, `vane`, and `kizuna`.

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
three max-host stack declarations in `stacks.toml` before applying the sync.

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
- `vllm` and `sglang` are profile-gated stacks. Komodo can track their compose
  files, but model lifecycle remains an explicit operator action.
