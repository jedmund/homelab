# infra_periphery

Standalone Komodo Periphery agent for hosts that are not the Komodo Core
host. It deploys to:

| Inventory host | Komodo Server | Address |
| --- | --- | --- |
| `max` | `Workstation` | `https://192.168.1.100:8120` |
| `gaming-pc` | `Gaming PC` | `https://192.168.1.12:8120` |
| `mac-mini` | `Mac mini` | `https://192.168.1.7:8120` |

Five Komodo stacks (`infra-periphery`, `beszel-agent-max`, `ai`, `vllm`,
`sglang`) depend on `max` via `server = "Workstation"` in
`komodo/stacks.toml`. Two (`infra-periphery-gaming-pc`,
`beszel-agent-gaming-pc`) depend on `gaming-pc` via `server = "Gaming PC"`.
`mac-mini` has no Ansible-rendered stacks, so no stack declares its Server;
Komodo shows its system stats and terminal.

Core (on `nuc-mini`, see `roles/infra_core`) connects inbound to
`https://<host>:8120`; UFW scopes 8120 to the core host's IP
(`firewall_group_komodo_periphery` in inventory on max, by hand on
gaming-pc). Docker's published-port rules run ahead of UFW, so the port is
reachable from the LAN regardless and the passkey is the effective gate; see
the caveat in `roles/firewall/defaults/main.yml`. The macOS application
firewall on mac-mini is off, so 8120 is open there as well.

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

## macOS (mac-mini)

On Darwin hosts the role runs the native `periphery-apple` release binary
as the user LaunchAgent `house.atelier.komodo-periphery` instead of the
container, so Komodo reports the Mac's own CPU, memory, and disk rather
than a Docker VM's. No sudo is needed; the play only escalates for the
Linux tasks.

- The binary is downloaded to `~/.komodo/bin/periphery-<version>` at
  `komodo_periphery_image_tag`. A tag bump downloads the new version and
  restarts the agent. Older binaries stay in that directory.
- Keys and the generated TLS certificate live under `~/.komodo`.
- The plist at `~/Library/LaunchAgents/house.atelier.komodo-periphery.plist`
  holds the passkey and is mode 0600.
- Logs go to `~/Library/Logs/komodo-periphery.log` and `.err.log`.
- `DOCKER_HOST` points at Colima's socket. Colima is not managed by this
  repository; without the socket, Periphery logs a container stats error
  on every poll but keeps serving.
- LaunchAgents start at login, so the agent depends on mac-mini logging
  in automatically, as the Paseo daemon and Beszel agent already do.

Periphery generates its certificate with the first `openssl` on `PATH`.
macOS's LibreSSL produces an X.509 v1 certificate, which Periphery's TLS
stack rejects with `UnsupportedCertVersion`, and the agent exits with
status 0. The role installs Homebrew `openssl@3` and puts it first on the
LaunchAgent's `PATH`. If `~/.komodo/ssl/cert.pem` ever reports
`Version: 1` in `openssl x509 -noout -text`, delete `~/.komodo/ssl` and
reload the agent so it regenerates the certificate.

To check the agent:

```sh
launchctl print gui/$(id -u)/house.atelier.komodo-periphery | grep -E 'state|pid'
tail ~/Library/Logs/komodo-periphery.log
```

To add the Server, create `Mac mini` in Komodo at
`https://192.168.1.7:8120`. It is always on, so keep its alerts enabled.

## AppArmor

The container runs with `apparmor:unconfined`. Periphery mounts the host's
`/proc` and reads each process's entries for system stats. Docker's default
profile treats those reads as ptrace and denied them about once a second,
which buried useful kernel messages on max. The container already has the
Docker socket, so the profile added no meaningful confinement.

## Version policy

Keep `komodo_periphery_image_tag` matched to `komodo_image_tag` in
`roles/infra_core/defaults/main.yml`; bump both together.
