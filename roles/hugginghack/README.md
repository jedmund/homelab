# HuggingHack

Deploys a Hugging Face model browser and PostgreSQL on `nuc-mini` at
`https://hf.atelier.house`. Downloaded models are stored on the NAS Files
share. Moving models to the inference host is a separate operation.

## Configuration

The application is built on the Docker host from the Git context in
`hugginghack_git_repo` and `hugginghack_git_ref`. The default ref is `main`.
It is not a registry-pulled application image. See
[defaults/main.yml](defaults/main.yml) and
[templates/compose.yaml.j2](templates/compose.yaml.j2).

Create `group_vars/hugginghack/vault.yml` with:

| Variable | Use |
| --- | --- |
| `vault_hugginghack_postgres_password` | Database password; use a URL-safe value because it is included in the connection URL |
| `vault_hugginghack_oidc_client_id` | PocketID confidential-client ID |
| `vault_hugginghack_oidc_client_secret` | PocketID client secret |
| `vault_hugginghack_hf_token` | Optional read token for private or gated model repositories |

Register the PocketID login callback as
`https://hf.atelier.house/api/auth/oidc/callback` and logout redirect as
`https://hf.atelier.house/`. Native OIDC is enabled; TinyAuth is disabled for
this route by default.

## Storage and deployment

Create `HuggingHack` at the root of the NAS Files share and allow writes by the
configured `puid:pgid`. The external `hugginghack-models` volume is declared in
[group_vars/compute_servers/storage.yml](../../group_vars/compute_servers/storage.yml).
The internal NFS export path includes `Files/.data`.

From the repository root:

```sh
make deploy-prerequisites
make -C deploy syntax STACK=hugginghack
make -C deploy hugginghack
```

Prerequisites apply host configuration as well as volumes. For an existing
host, first check whether the required network and volume already exist.

The role starts PostgreSQL, builds the application, checks the retained owner
when the old SQLite file is present, and starts the full stack. Its final
health check requires PostgreSQL, OIDC, and filesystem object storage.

| Data | Location |
| --- | --- |
| Models | External `hugginghack-models` NFS volume, mounted at `/models` |
| Application files | `/opt/docker/hugginghack/data`, mounted at `/data` |
| PostgreSQL | Compose-managed `hugginghack-pgdata` volume |

The SQLite-to-PostgreSQL conversion and PocketID owner-link migration are
complete. Routine deployment no longer converts an old database. See the
[retirement record](../../docs/retired-migrations.md) when restoring an older
backup. Keep existing pre-migration SQLite backups until recovery requirements
have been reviewed.

## Import an older model directory

The model-directory script is separate from the retired database migration.
With the Files share mounted on the control machine, preview moves from
`Files/models` into the HuggingHack library:

```sh
make migrate-hugginghack-models FILES_ROOT=/Volumes/Files
```

Review the source and destination paths, then apply:

```sh
make migrate-hugginghack-models-apply FILES_ROOT=/Volumes/Files
```

The script refuses destination conflicts. It does not deploy a model to `max`.
