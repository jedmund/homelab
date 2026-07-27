# Matrix

The Matrix stack contains Synapse, Element Web, synapse-admin, Matrix
Authentication Service (MAS), LiveKit, two PostgreSQL databases, and the
LiveKit JWT service.

## Vault

Create `group_vars/matrix/vault.yml` with:

```yaml
synapse_db_password: <postgres-password>
synapse_registration_shared_secret: <registration-secret>
livekit_api_key: <livekit-key>
livekit_api_secret: <livekit-secret>
synapse_s3_access_key_id: <media-storage-access-key>
synapse_s3_secret_access_key: <media-storage-secret-key>
mas_db_password: <mas-postgres-password>
mas_synapse_shared_secret: <mas-synapse-secret>
mas_encryption_key: <64-hex-characters>
mas_oidc_client_id: <pocketid-client-id>
mas_oidc_client_secret: <pocketid-client-secret>
```

Generate independent random values for the registration, LiveKit, MAS, and
database secrets. `mas_encryption_key` must be exactly 64 hexadecimal
characters.

The role generates the Synapse and MAS signing private keys once on the host,
with mode `0600`; they are not vault inputs and must be included in host-level
backups.

## Local image build

Synapse uses a small role-owned Dockerfile layered on the upstream image. It
is one of the accepted build-on-host exceptions documented in
[CONVENTIONS.md](../../CONVENTIONS.md).

## OIDC

MAS delegates authentication to PocketID. Register the MAS upstream client in
PocketID, then place its client ID and secret in the Matrix vault before
deploying.
