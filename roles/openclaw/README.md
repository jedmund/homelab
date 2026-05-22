# Openclaw

Native macOS install on `mac-mini`. Openclaw runs as a launchd LaunchAgent
in the user session so it can reach iMessage, the Spark Desktop MCP, and
the Apple-app MCPs (Notes, Calendar, Reminders, Mail, Messages). None of
those work from a Linux container, which is why this role doesn't follow
the repo's usual Docker-compose pattern.

## What the role does

- Installs `node@24` via Homebrew (Openclaw recommends Node 24).
- Installs `openclaw` globally via that Node's npm.
- Writes `~/.openclaw/openclaw.json` with:
  - sandbox mode `off` (tool exec runs on the host),
  - a `local` OpenAI-compatible provider pointing at llama-swap on `max`
    (`http://192.168.1.100:11434/v1`).

## One-time manual bring-up

After the role runs (or the first time you stand up Openclaw on a new
Mac), do this on the mac-mini console (not over SSH):

1. **Install the daemon.** `openclaw onboard --install-daemon`. This is
   interactive and writes the launchd plist. Approve any macOS prompts.
2. **Grant macOS permissions.** Open System Settings and approve, as they
   appear:
   - Local Network (per the repo-wide gotcha for brew daemons),
   - Automation / Accessibility (for AppleScript-driven channels),
   - Full Disk Access (for Messages/Notes/Calendar reads),
   - Notifications (so iMessage replies surface).
3. **Confirm the gateway is listening.** `curl -s
   http://127.0.0.1:18789/health` or open the Control UI in a browser.
4. **Note the launchd label.** `launchctl list | grep -i openclaw` --
   record it so future config changes can be applied with
   `launchctl kickstart -k gui/$(id -u)/<label>`.
5. **Verify the Traefik route.** Hit https://openclaw.atelier.house from
   another device; it should land on the mac-mini through TinyAuth.

## Channel + MCP wiring

Channels (iMessage, Slack, etc.) and MCP servers (Spark, Apple apps) are
configured via the Openclaw Control UI rather than this role's config
template. Once those are dialed in, export the resulting
`~/.openclaw/openclaw.json` and fold the additions back into
`templates/openclaw.json.j2` so the config is reproducible.

## Why no Docker sandbox

Sandboxing via Docker on macOS means Docker Desktop or OrbStack spinning
up a Linux VM: heavier RAM, slower bind mounts, sandbox image is Debian
inside the VM. The mac-mini doesn't carry sensitive files (those live on
nuc-mini), so the trust trade is fine. If that changes, set
`openclaw_sandbox_mode` to `non-main` or `all` and switch the backend to
SSH against nuc-mini so sandboxed exec ships to a Linux host.
