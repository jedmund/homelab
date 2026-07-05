# infra_periphery

Standalone Komodo Periphery agent for hosts that are not the Komodo Core
host. Currently deploys to `max`, which four Komodo stacks (`ai`, `vllm`,
`sglang`, `beszel-agent-max`) depend on via `server = "max"` in
`komodo/stacks.toml`.

Core (on `nuc-mini`, see `roles/infra_core`) connects inbound to
`https://<max>:8120`; UFW scopes 8120 to the core host's IP
(`firewall_group_komodo_periphery` in inventory).

## First deploy: taking over from an unmanaged agent

Before this role existed, the Periphery agent on `max` was installed out
of band. If an unmanaged periphery (systemd unit or container) is still
running there, it holds :8120 and the compose deploy will fail to bind.
Before the first `make deploy-infra-periphery`:

1. Find the old agent: `systemctl list-units | grep -i periphery` and
   `docker ps | grep periphery`.
2. Stop and disable it (`systemctl disable --now <unit>` or
   `docker rm -f <container>`).
3. Deploy, then confirm the `max` Server resource reconnects in the
   Komodo UI (it should point at `https://192.168.1.100:8120`).

The passkey in `group_vars/infra_periphery/vault.yml` must equal
`komodo_passkey` in `group_vars/infra_core/vault.yml`, or Core's
connection is rejected.

## Version policy

Keep `komodo_periphery_image_tag` matched to `komodo_image_tag` in
`roles/infra_core/defaults/main.yml`; bump both together.
