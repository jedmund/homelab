# Beszel

Beszel hub runs on `nuc-mini`; `beszel_agent` installs the monitored agents on
`max`, `nuc-mini`, and `mac-mini`.

## First bootstrap

1. Deploy the gateway so the DNS label and route exist, then deploy the hub:

   ```sh
   make deploy-infra-gateway
   make deploy-beszel
   ```

2. Create the first administrator at `https://beszel.atelier.house`.
3. Register a PocketID application with redirect URI:

   ```text
   https://beszel.atelier.house/api/oauth2-redirect
   ```

4. In Beszel's superuser UI at `https://beszel.atelier.house/_/`, temporarily
   show collection controls, edit the users collection, enable OAuth2, add the
   PocketID OIDC provider, and hide collection controls again.
5. Create or enable a permanent universal token under `/settings/tokens`.
   Save the token and the public `KEY` from Beszel's generated agent command
   in `group_vars/beszel_agents/vault.yml`:

   ```yaml
   vault_beszel_agent_token: <permanent-universal-token>
   vault_beszel_agent_key: <hub-public-key>
   ```

6. Deploy the agents:

   ```sh
   make deploy-beszel-agents
   ```

The hub itself has no vault inputs. Do not use a short-lived registration
token for unattended agent reconciliation.
