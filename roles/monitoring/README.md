# Netdata monitoring

The `monitoring` role installs native Netdata on every `compute_servers` host.
`nuc-mini` is the streaming parent with long retention; the other machines are
children with short local retention.

This is separate from the Beszel hub and agent roles.

## Vault

Generate one streaming key and store it in
`group_vars/compute_servers/vault.yml`:

```sh
openssl rand -hex 16
```

```yaml
vault_netdata_stream_api_key: <shared-streaming-key>
```

Every parent and child must use the same key.

## Deployment

Netdata is part of the prerequisites play:

```sh
make deploy-prerequisites
```

On Debian/Ubuntu the role uses Netdata's stable-channel installer and a
systemd service. On macOS it installs Netdata with Homebrew and manages it as
a brew service. Streaming configuration contains the shared key and is
written with restricted permissions.
