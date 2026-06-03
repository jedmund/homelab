# group_vars/openclaw/

Holds the encrypted `vault.yml` for the `openclaw` stack (native macOS
install on `mac-mini`, see `roles/openclaw/`).

## Bootstrapping `vault.yml`

Create the file via the vault CLI; the role's `defaults/main.yml`
references `vault_*` variables that must be defined here (or the deploy
will fail with "undefined variable").

```bash
ansible-vault create group_vars/openclaw/vault.yml
# or, if you'd rather use a temp file first:
make encrypt FILE=group_vars/openclaw/vault.yml
```

### Variables that must be present in `group_vars/openclaw/vault.yml`

Discord channel (required while `openclaw_discord_enabled: true`):

- `vault_openclaw_discord_bot_token` — bot token from the Discord
  Developer Portal, Bot tab. Treat as a password.
- `vault_openclaw_discord_user_id` — your own Discord user ID
  (snowflake). Enable Developer Mode in Discord settings, then
  right-click your profile, Copy User ID.
- `vault_openclaw_discord_application_id` — Application ID from the
  Developer Portal, General Information tab. Improves daemon startup.

Google Places skill (required while `openclaw_goplaces_enabled: true`):

- `vault_openclaw_google_places_api_key` — API key from
  console.cloud.google.com. Enable the Places API on a project, create
  an API key, restrict the key to Places API. Treat as a secret.

To stand up Openclaw without one of these features, flip its
`openclaw_<feature>_enabled` to `false` (in
`group_vars/openclaw/main.yml` or via `-e` at deploy time) and omit the
matching vault entries.
