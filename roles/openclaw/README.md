# Openclaw

Native macOS install on `mac-mini`. Openclaw runs as a launchd LaunchAgent
in the user session so it can reach iMessage, the Spark Desktop MCP, and
the Apple-app MCPs (Notes, Calendar, Reminders, Mail, Messages). None of
those work from a Linux container, which is why this role doesn't follow
the repo's usual Docker-compose pattern.

## What the role does

- Installs `node@24` via Homebrew (Openclaw recommends Node 24).
- Installs `openclaw` globally via that Node's npm.
- Templates `~/.openclaw/.env` from vault on every deploy (Discord bot
  token, etc.); the gateway loads this at startup.
- **Bootstrap-only** writes `~/.openclaw/openclaw.json` the first time
  (sandbox off, `local` provider pointing at llama-swap on `max`, both
  declared models, `tools.web.fetch.useTrustedEnvProxy` if proxy enabled).
  After that the file is owned by `openclaw onboard` and the Control UI;
  the role leaves it alone (`force: false` on the template). To reset to
  the templated bootstrap, delete `~/.openclaw/openclaw.json` on the
  mac-mini and re-run the deploy.
- **Tinyproxy + service-env patch** when `openclaw_proxy_enabled` is true
  (default). Installs `tinyproxy` via Homebrew, templates a loopback-only
  config, starts it via `brew services`, and `blockinfile`-patches
  `~/.openclaw/service-env/ai.openclaw.gateway.env` with `HTTPS_PROXY`
  pointing at the local proxy. See the next section for the rationale.

## Why the local proxy

Openclaw's built-in `web_fetch` tool has a hard-coded SSRF guard that
blocks any URL whose hostname resolves to a private/internal IP (see
`/opt/homebrew/lib/node_modules/openclaw/dist/fetch-guard.js`). The
`tools.web.fetch.ssrfPolicy` schema only accepts narrow opt-ins for
fake-IP proxy ranges (`allowRfc2544BenchmarkRange`,
`allowIpv6UniqueLocalRange`); no hostname allowlist field exists for that
tool. Without a workaround, openclaw cannot fetch any `*.atelier.house`
URL (they resolve locally to `192.168.1.6`).

The blessed escape hatch is `tools.web.fetch.useTrustedEnvProxy: true`
paired with an actual HTTP proxy. When that flag is on and `HTTPS_PROXY`
is set, openclaw skips its own DNS lookup and the "resolves to private
IP" check because the proxy is the one resolving DNS. Public URLs still
work (the proxy forwards them too). Set:

- `openclaw_proxy_enabled` (default `true`) toggles the whole thing.
- `openclaw_proxy_port` (default `8888`) is the tinyproxy listen port.
- `openclaw_proxy_no_proxy` defaults to a comma-separated list of
  loopback addresses plus the `max` server's IP, so llama-swap / TEI /
  SearXNG calls bypass the proxy on the hot path. Add to it if you want
  other LAN IPs to skip the proxy hop.

After `openclaw onboard --install-daemon` runs, **macOS will silently
block tinyproxy's LAN connections until you approve Local Network for
it in System Settings -> Privacy & Security -> Local Network**. The
service-env block injection in the role waits until openclaw has
created the service-env file (i.e. after onboarding) before applying;
on first deploy the role surfaces a reminder and the patch lands on the
next playbook run.

## One-time manual bring-up

After the role runs (or the first time you stand up Openclaw on a new
Mac), do this on the mac-mini console (not over SSH):

1. **Install the daemon.** `openclaw onboard --install-daemon`. This is
   interactive and writes the launchd plist. Approve any macOS prompts.
2. **Grant macOS permissions.** Open System Settings and approve, as they
   appear:
   - Local Network for **both** `openclaw` and `tinyproxy` (per the
     repo-wide gotcha for brew daemons; tinyproxy needs LAN access to
     reach the homelab services openclaw fetches),
   - Automation / Accessibility (for AppleScript-driven channels),
   - Full Disk Access (for Messages/Notes/Calendar reads),
   - Notifications (so iMessage replies surface).
3. **Confirm the gateway is listening.** `curl -s
   http://127.0.0.1:18789/health` or open the Control UI in a browser.
4. **Note the launchd label.** `launchctl list | grep -i openclaw` --
   record it so future config changes can be applied with
   `launchctl kickstart -k gui/$(id -u)/<label>`.
5. **Verify the Traefik route.** Hit https://claw.atelier.house from
   another device; it should land on the mac-mini through TinyAuth.
   Requires `openclaw config set gateway.bind 'lan'` first (the wizard
   defaults to loopback, which blocks LAN access).

## Discord channel (DM-only personal bot)

Discord is wired through the role's config template, gated by
`openclaw_discord_enabled` (default true). Setup is one-time on the
Discord side:

1. **Create the application.** Discord Developer Portal then New
   Application. Name it (e.g. "Openclaw"). On the **Bot** tab, set
   "Public Bot" to off. If you hit "Private application cannot have a
   default authorization link", go to **Installation** and set Install
   Link to "None", then save.
2. **Enable intents.** On the Bot tab, enable **Message Content
   Intent** (required) and optionally Server Members Intent.
3. **Grab the token.** Bot tab, Reset Token. This is
   `vault_openclaw_discord_bot_token`. Treat as a password.
4. **Grab IDs.** In Discord, enable Developer Mode (Settings, Advanced,
   Developer Mode), then right-click your own profile, Copy User ID.
   That's `vault_openclaw_discord_user_id`. The Application ID is on
   the Developer Portal General Information tab; that's
   `vault_openclaw_discord_application_id` (improves daemon startup).
5. **Invite the bot.** Openclaw only supports Guild Install, not User
   Install. OAuth2, URL Generator, integration type "Guild Install",
   scopes: `bot` + `applications.commands`. Bot Permissions: Send
   Messages, Read Message History, Embed Links, Attach Files
   (optionally Use Slash Commands). Generate the URL, invite the bot
   to any server you're in (a private one-person server is fine; the
   role's config sets `groupPolicy: "disabled"` so server traffic is
   ignored).
6. **Add the vault entries**, then re-run `make deploy-openclaw` and
   restart the gateway daemon (`launchctl kickstart -k
   gui/$(id -u)/<label>`). DM the bot to confirm it responds.

To disable Discord entirely set `openclaw_discord_enabled: false` in
a host_vars/group_vars override; the channels block is then omitted
from the rendered config.

## Other channels + MCP wiring

Channels other than Discord (iMessage, Slack, etc.) and MCP servers
(Spark, Apple apps) are configured via the Openclaw Control UI rather
than this role's config template. Once those are dialed in, export the
resulting `~/.openclaw/openclaw.json` and fold the additions back into
`templates/openclaw.json.j2` so the config is reproducible.

## Why no Docker sandbox

Sandboxing via Docker on macOS means Docker Desktop or OrbStack spinning
up a Linux VM: heavier RAM, slower bind mounts, sandbox image is Debian
inside the VM. The mac-mini doesn't carry sensitive files (those live on
nuc-mini), so the trust trade is fine. If that changes, set
`openclaw_sandbox_mode` to `non-main` or `all` and switch the backend to
SSH against nuc-mini so sandboxed exec ships to a Linux host.
