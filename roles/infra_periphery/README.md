# infra_periphery

Standalone Komodo Periphery agent for hosts that are not the Komodo Core
host. It deploys to:

| Inventory host | Komodo Server | Address |
| --- | --- | --- |
| `max` | `Workstation` | `https://192.168.1.100:8120` |
| `gaming-pc` | `Gaming PC` | `https://192.168.1.12:8120` |

Five Komodo stacks (`infra-periphery`, `beszel-agent-max`, `ai`, `vllm`,
`sglang`) depend on `max` via `server = "Workstation"` in
`komodo/stacks.toml`. Two (`infra-periphery-gaming-pc`,
`beszel-agent-gaming-pc`) depend on `gaming-pc` via `server = "Gaming PC"`.

Core (on `nuc-mini`, see `roles/infra_core`) connects inbound to
`https://<host>:8120`; UFW scopes 8120 to the core host's IP
(`firewall_group_komodo_periphery` in inventory on max, by hand on
gaming-pc). Docker's published-port rules run ahead of UFW, so the port is
reachable from the LAN regardless and the passkey is the effective gate; see
the caveat in `roles/firewall/defaults/main.yml`.

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

## gaming-pc: one-time host setup

`gaming-pc` runs CachyOS (Arch). It sets `skip_prerequisites: true` because
the `prerequisites`, `docker`, and `firewall` roles are apt-based, so the
host is prepared by hand before the first deploy. Run on the PC:

```sh
# Passwordless sudo for Ansible, as roles/prerequisites sets on Ubuntu hosts.
# visudo validates the file before installing it.
echo 'justin ALL=(ALL) NOPASSWD: ALL' | sudo EDITOR='tee' visudo -f /etc/sudoers.d/justin

# NVIDIA runtime for the beszel-agent-nvidia GPU collector
sudo pacman -S --needed nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker

# Docker is installed but disabled by default
sudo systemctl enable --now docker

# Match max's UFW rule for Periphery (see the Docker caveat above)
sudo ufw allow proto tcp from 192.168.1.6 to any port 8120 comment 'Komodo Periphery (core host only)'
```

Then, from the main checkout (not a worktree), with the PC on:

```sh
make deploy-limit HOST=gaming-pc
```

`deploy/all.yml` skips the prerequisites and Netdata plays on this host and
deploys `beszel_agent` and `infra_periphery`. Finish in the Komodo UI:

1. Create the Server `Gaming PC` at `https://192.168.1.12:8120`.
2. Turn off its unreachable alerts before saving. The `homelab-operations`
   Alerter subscribes to `ServerUnreachable`, and this machine is often off
   or booted into Windows.
3. Refresh the Resource Sync preview. It should add
   `infra-periphery-gaming-pc` and `beszel-agent-gaming-pc` with no
   deletions.

The Beszel agent registers itself with the hub through the universal token.
Confirm `gaming-pc` appears in Beszel with a GPU panel.

## AppArmor

The container runs with `apparmor:unconfined`. Periphery mounts the host's
`/proc` and reads each process's entries for system stats. Docker's default
profile treats those reads as ptrace and denied them about once a second,
which buried useful kernel messages on max. The container already has the
Docker socket, so the profile added no meaningful confinement.

## Version policy

Keep `komodo_periphery_image_tag` matched to `komodo_image_tag` in
`roles/infra_core/defaults/main.yml`; bump both together.
