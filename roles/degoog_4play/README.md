# Degoog 4play native browser

This role runs the official Degoog 4play Firefox client on `nuc-mini`. It is
experimental and is intentionally excluded from `deploy/all.yml`.

## Prerequisites

- The Degoog stack and official 4play transport must be deployed on `max`.
- `group_vars/degoog/vault.yml` must contain `vault_degoog_4play_password`.
- `nuc-mini` must have a connected display adapter with EDID. The Comet X
  passthrough currently provides this; an HDMI EDID dummy can be used instead.

## Deploy

Run from the repository root:

```sh
make deploy-degoog
make -C deploy degoog_4play
```

The role installs a pinned Mozilla Firefox release, Xorg, XFCE, and a
host-local Nginx WebSocket bridge. Xorg uses display `:1` and `-nolisten tcp`;
the bridge listens only on `127.0.0.1:3031`. Existing Docker services and the
public search route are not reconfigured by this role.

Firefox runs under the locked `degoog-firefox` account. The 4play extension is
force-installed through Firefox enterprise policy, and its local WebSocket
settings are seeded by the managed profile bootstrap before Firefox starts.

## Verify

```sh
systemctl --no-pager --full status \
  degoog-4play-bridge.service \
  degoog-4play-xorg.service \
  degoog-4play-session.service \
  degoog-4play-firefox.service
DISPLAY=:1 xrandr --query
ss -ltn | grep ':3031'
```

The bridge must be bound only to loopback. Xorg must report a connected EDID
backed output, and Firefox must be running as `degoog-firefox`.

## Recovery

If Xorg cannot start, verify the Comet X input is switched to the NUC or plug
in the HDMI EDID dummy, then rerun the playbook. Do not edit the generated
systemd units, Firefox policy, profile settings, or bridge configuration by
hand; rerun Ansible after correcting the input or repository configuration.
