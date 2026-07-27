# HuggingHack

HuggingHack is a local-first Hugging Face model browser and downloader on
`nuc-mini`. Models land on the NAS-backed Files share before they are promoted
to the serving host.

Upstream does not publish a container image. The role builds directly from the
commit pinned by `hugginghack_version` in `defaults/main.yml`; bump that commit
to roll forward.

## Vault

`group_vars/hugginghack/vault.yml` may define:

```yaml
vault_hugginghack_hf_token: <optional-read-only-token>
```

The token is needed only for private or gated repositories.

## First deployment

The external `hugginghack-models` volume points inside the Files export. On a
fresh setup:

1. Create `HuggingHack` at the root of the visible Files share. Its internal
   export path is `Files/.data/HuggingHack`.
2. Make that directory writable by the configured `puid:pgid`.
3. Create the NFS volume, then deploy the service:

   ```sh
   make deploy-prerequisites
   make deploy-hugginghack
   ```

The container health check verifies that the model storage is writable.

## Migrating an older model layout

Models previously stored under `Files/models` can be reorganized into the
owner/repository layout. Mount the Files share locally and preview first:

```sh
make migrate-hugginghack-models FILES_ROOT=/Volumes/Files
```

Apply only after reviewing the preview:

```sh
make migrate-hugginghack-models-apply FILES_ROOT=/Volumes/Files
```

The migration refuses destination conflicts and is safe to rerun after
already-completed moves.
