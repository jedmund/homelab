# group_vars/hermes/

Holds the encrypted `vault.yml` for the Hermes Agent dashboard stack
(native macOS install on `mac-mini`, see `roles/hermes/`).

## Bootstrapping `vault.yml`

```bash
ansible-vault create group_vars/hermes/vault.yml
```

Required variables:

- `vault_hermes_dashboard_basic_auth_secret` - stable token signing
  secret. Generate with `openssl rand -base64 32`.
- `vault_hermes_dashboard_basic_auth_password_hash` - preferred
  username/password auth credential.

Instead of a hash you can set
`vault_hermes_dashboard_basic_auth_password` for initial bootstrap. The
role also accepts `vault_hermes_dashboard_basic_auth_username`; it defaults
to `admin` when omitted.
