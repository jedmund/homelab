# group_vars/reading/

Holds the encrypted `vault.yml` for the `reading` stack (Miniflux,
Reactflux, FiveFilters, Karakeep, Kavita).

## Bootstrapping `vault.yml`

The new stack inherits secrets that used to live in
`group_vars/media_consumption/vault.yml`. Copy them across, add the new
FiveFilters admin password, then trim the originals from
`media_consumption` once the move is verified.

```bash
# 1. Copy the existing vault as a starting point (already encrypted)
cp group_vars/media_consumption/vault.yml group_vars/reading/vault.yml

# 2. Edit and trim to just what `reading` needs, plus add fivefilters_admin_password
make edit-vault FILE=group_vars/reading/vault.yml
```

### Variables that must be present in `group_vars/reading/vault.yml`

Copy from `group_vars/media_consumption/vault.yml`:

- `miniflux_admin_password`
- `miniflux_db_password`
- `miniflux_oauth2_client_id`
- `miniflux_oauth2_client_secret`
- `karakeep_nextauth_secret`
- `karakeep_meili_master_key`
- `karakeep_oauth_client_id`
- `karakeep_oauth_client_secret`
- `karakeep_openai_api_key` (if defined)

Add new:

- `fivefilters_admin_password` — admin password for the FiveFilters
  config UI exposed at `http://nuc-mini:8181/admin`.

### After verifying the new stack works

Trim the moved keys (`miniflux_*`, `karakeep_*`) out of
`group_vars/media_consumption/vault.yml`:

```bash
make edit-vault FILE=group_vars/media_consumption/vault.yml
```
