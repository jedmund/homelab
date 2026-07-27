# Vane

Vane is an in-house Perplexity-style answer engine. GitLab CI builds the image
and publishes `latest` plus commit tags; this role authenticates to the
registry and pulls the selected `vane_image_tag`.

Vane reuses SearXNG from the `ai` stack on `max`.

## Vault

Create `group_vars/vane/vault.yml` with:

```yaml
vault_vane_registry_username: <read-registry-deploy-token-user>
vault_vane_registry_password: <read-registry-deploy-token>
vault_vane_oidc_client_id: <pocketid-client-id>
vault_vane_oidc_client_secret: <pocketid-client-secret>
vault_vane_session_secret: <random-string-at-least-32-characters>
```

Register the PocketID client with:

```text
https://vane.atelier.house/api/auth/callback
```

## First split deployment

The role deliberately mounts the existing `utilities_vane-data` volume so the
move to a standalone stack does not migrate application data.

After `make deploy-vane`:

1. Verify the `vane` container mounted that volume at the expected path.
2. Create a Komodo Stack named `vane`, enable files-on-host, and use
   `/opt/docker/vane` as its project source.
3. Set `KOMODO_URL`, `KOMODO_API_KEY`, `KOMODO_API_SECRET`, and
   `KOMODO_VANE_STACK=vane` in the Vane GitLab project.

CI-triggered deployments and Ansible will then reconcile the same rendered
Compose project.
