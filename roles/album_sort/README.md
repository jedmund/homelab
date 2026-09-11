# Album Sort M4 cutover

M4 replaces disposable probe authentication with named per-user credentials.
Deploy the complete application stack once, not intermediate auth branches.

## Preflight and ordering

1. Back up the database using SQLite's online backup and verify integrity. Keep
   the pre-cutover image reference and configuration privately for rollback.
2. Provision `vault_album_sort_user_secret_encryption_key` in the local encrypted
   Album Sort vault (or ignored `group_vars/album_sort/local_m4_key.yml`):
   canonical base64 of 32 random bytes. Back up that encrypted
   vault independently of the database. Never generate a replacement during deploy
   or print the key in playbook output. Vault files remain untracked.
3. Deploy Traefik first. Inventory pins its observed proxy-network IPv4 address;
   check this still belongs to Traefik before applying. The static HTTP redirect
   priority changes, so this step recreates the shared proxy and briefly interrupts
   other proxied services. Preserve ACME state. Do not use a subnet trust fallback.
4. Deploy Album Sort with the approved full-stack immutable image tag. The role
   checks Traefik's current address against the pin and trusts only that /32.
   Remove retired probe secrets from the vault after rollback no longer needs them;
   the new environment template never deploys them or the old trace-path setting.
5. Verify `/healthz`, browser OIDC login, anonymous HTTPS extension discovery,
   anonymous private-method denial, and plain-HTTP `/rest` rejection without a
   redirect. HTTPS and HTTP routers explicitly overwrite X-Forwarded-Proto.
6. Run the application's M4 proxy-redaction verifier against the approved image,
   review all log collectors, then run the finite owner client-auth capture.
   Reconfigure retained clients with their own named credentials; probe profiles
   stop working at cutover. Never borrow browser cookies for CLI authentication.

## HTTP and log boundary

Before publication, run `ansible-playbook deploy/verify_album_sort_m4.yml` for
local render-only assertions, plus `ansible-playbook deploy/album_sort.yml
--syntax-check` and `ansible-playbook deploy/traefik.yml --syntax-check`.

The HTTP `/rest` router uses priority 2147482647, above the entrypoint redirect's
2147482646 but within Traefik's reserved-priority limit. Other HTTP routes retain
the catch-all redirect. The HTTP route forwards an explicit `http` assertion so
the application rejects before authentication, even if the caller spoofs `https`.
See [Traefik entrypoint priority](https://doc.traefik.io/traefik/v3.3/routing/entrypoints/#priority).

Traefik access logs drop query parameters. Keep Docker JSON logging at 10 MiB
with at least three files and review additional collectors before marker tests.
No real credential belongs in a test URL, shell argument, log, commit or PR.
The application's verifier checks all four reviewed sinks; configuration alone
is not acceptance evidence. Health-check paths and timeouts are unchanged.

## Rollback and proxy changes

Before named credential issuance, restore the pre-cutover configuration/image
only under the application's migration compatibility procedure. After issuance,
use a compatible M4 image or withdraw `/rest` while restoring the verified backup
and invalidating restored credentials. Never revive a probe key silently.

If the proxy network is rebuilt, explicitly update the pinned Traefik address and
redeploy Album Sort together. A stale or missing peer must fail closed, not trust
the network pool. Preserve the encryption key across ordinary image upgrades.
