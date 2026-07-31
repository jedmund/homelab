# RomM

ROM library manager at `rom.atelier.house`, running on nuc-mini.

Most of the role is unremarkable. This file covers the one part that is
not: emulator streaming, which spans four roles and two hosts.

## Emulator streaming

RomM 5.1 can launch a game into a native emulator running in a separate
container and stream the picture, sound, and input back to the browser.
Unlike EmulatorJS the emulation runs server-side on real binaries, so the
host does the work rather than the client.

Two containers are wired up, both on max:

| Platform slugs | Emulator | Role           | Selkies       | Broker     |
| -------------- | -------- | -------------- | ------------- | ---------- |
| `ps2`          | PCSX2    | `roles/pcsx2`  | max:3010/3011 | max:8010   |
| `ngc`, `wii`   | Dolphin  | `roles/dolphin`| max:3020/3021 | max:8020   |

RomM's own docs list `wiiu` against Dolphin. Dolphin does not emulate the
Wii U, so that slug is not configured.

### Why max and not nuc-mini

RomM runs on nuc-mini, so putting the emulators there would have kept
everything on one box and let the brokers stay on an internal Docker
network. They are on max anyway, because emulation is overwhelmingly
single-thread CPU bound and the Threadripper is far ahead of nuc-mini's
Core Ultra 7 on that axis. PCSX2 in particular would have been marginal
on the NUC. The GPUs mostly just need to exist.

The cost of that choice is that every hop between RomM and the emulators
is now cross-host: `broker_host` has to be a LAN address rather than a
container name, and the broker ports are exposed on max's LAN interface
with only the shared secret guarding them. `roles/firewall` pins them to
nuc-mini's address so nothing else on the LAN can reach them.

### VRAM contention

Both emulators are pinned to nvidia-smi device 2, the 600 W Workstation
Edition card. This is a tradeoff, not a free lunch. `ai_gpu_mode: split`
(`roles/ai/defaults/main.yml`) puts llama-swap on that same device, and
`shared` puts it there too. There is no card that is reliably idle.

An emulator needs on the order of 1-2 GB of VRAM and almost no compute,
so it fits alongside a model. The hazard is ordering: llama.cpp and vLLM
size their allocations against whatever is free at load time, so an
emulator that starts first shrinks a later model load, and a large model
that loads first can leave too little for the emulator. If that becomes a
real problem, take a card out of `ai_gpu_devices` and give it to the
emulators outright.

## Host prerequisites on max

None of these are handled by Ansible, and at the time of writing **none
of them are satisfied**. The roles will deploy but the containers will
not come up until these are done.

### 1. The NVIDIA driver is mismatched

```
$ nvidia-smi
Failed to initialize NVML: Driver/library version mismatch
```

The loaded kernel module is 580.159.03 while userspace is at 580.173.02:
an apt upgrade landed a new driver without a reboot. Containers started
before the upgrade still hold the old module and keep running, which is
why the AI stack looks fine, but anything new that asks for a GPU will
fail to start.

Both `nvidia-dkms-580-server` (580.126.20) and
`nvidia-dkms-580-server-open` (580.173.02) are installed, which is
probably how the versions drifted apart in the first place. Worth
resolving to one before rebooting.

### 2. DRM kernel parameters are missing

LinuxServer's Selkies images need the NVIDIA DRM layer up for a headless
GL context:

```
nvidia-drm.modeset=1 nvidia_drm.fbdev=1
```

`/proc/cmdline` on max currently has only `amd_iommu=pt iommu=pt`. GRUB
is not managed by this repo, so add these to `GRUB_CMDLINE_LINUX_DEFAULT`
in `/etc/default/grub`, run `update-grub`, and reboot. Keep the existing
IOMMU flags: they are load-bearing for multi-GPU NCCL P2P.

LinuxServer also documents a dummy plug on headless systems for DRM to
initialise properly. Whether that is actually required on a Blackwell
with the open module is untested here. If the containers come up but the
stream is black, that is the first thing to suspect.

### 3. PS2 BIOS

PCSX2 needs a BIOS dump in `/opt/docker/pcsx2/config/bios`. The role
creates the directory and warns when it is empty, but cannot supply the
file. Without it PCSX2 parks on an error dialog rather than crashing, so
`/status` reports healthy while nothing plays.

### 4. PCSX2 memory card type

In-game save sync needs the Slot 1 memory card to be `Folder` type, not
`File`. Set it in the PCSX2 UI under Settings, Memory Cards. A `File`
card is one 8 MB blob holding every game's saves together, so there is no
way to sync a single game out of it, and `/memory-card` returns 409.

Dolphin's equivalent is a GCI folder card in Slot A, which the broker
derives automatically.

## Vault variables

```yaml
vault_romm_streaming_broker_secret: <shared secret>
vault_pcsx2_selkies_password: <basic auth password>
vault_dolphin_selkies_password: <basic auth password>
```

The broker secret has to be identical in all three roles. RomM sends it
as `X-Broker-Secret` on every call; an empty value at the broker end
means every request is accepted.

## Authentication

Two layers, for two different paths:

- **Through Traefik** (`pcsx2.atelier.house`, `dolphin.atelier.house`):
  TinyAuth, per the usual pattern for services on max.
- **Direct to max on 3011/3021**: the container's own Selkies basic auth,
  from `CUSTOM_USER` and `PASSWORD`. Unset, these images default to
  `abc`/`abc`, which is why they are set even though Traefik is the
  normal path.

There is a wrinkle. RomM embeds the stream in its player view, and a
forward-auth redirect cannot complete inside that frame. The first visit
of a session has to be to `pcsx2.atelier.house` or
`dolphin.atelier.house` directly; after that the TinyAuth cookie covers
the embed.

## config.yml is co-owned

The `streaming` block lives in `config.yml`, not in env vars. That file
is also a two-way editor target for RomM's Library Management UI, which
already owns the exclude rules and emulatorjs settings on this instance.

The role therefore does not template the file. It reads the existing one,
merges only the `streaming` key, and writes it back, so UI-authored keys
survive a deploy. The first run reformats the file, since the merge is
done through a YAML round trip; runs after that are idempotent.

Editing the streaming block through the UI will work until the next
deploy overwrites it. Change it in `defaults/main.yml` instead.

## Verifying

The streaming config is fetched when the RomM frontend loads, so refresh
after a deploy.

```bash
# What RomM thinks it has
curl -s https://rom.atelier.house/api/streaming/config | jq

# Broker reachability, from nuc-mini (health skips the secret check)
curl -s http://192.168.1.100:8010/health
curl -s http://192.168.1.100:8020/health

# Session state. `active` is true even on the idle dashboard, so check
# rom_path to tell whether a game is actually running.
curl -s -H "X-Broker-Secret: $SECRET" http://192.168.1.100:8010/status | jq
```

No play action on a game means `streaming.enabled` is false, no container
is configured for that platform slug, or the frontend has stale config.

## Known unknown: the WebRTC media path

Selkies signalling rides the HTTPS websocket, which Traefik proxies
fine. The media path is the part not proven here. Current Selkies
versions carry video over the same websocket, which is consistent with
LinuxServer documenting only 3000 and 3001 and nothing UDP, and if that
holds then Traefik covers the whole thing and the firewall rules in this
repo are sufficient.

If instead it negotiates ICE and wants UDP directly to max, remote access
will need a TURN relay, and there is no coturn role in this repo. LAN
access would still work. Worth confirming with one container before
building anything else on top of this.
