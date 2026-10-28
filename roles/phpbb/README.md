# phpBB board

phpBB forum at `board.fireplace.cafe`, built from the pinned official phpBB
release. The stack has three services: the board application (host-built
image: `php:8.4.27-fpm-alpine3.24` plus phpBB 3.3.19 and its PHP
extensions), an nginx origin container behind Traefik, and MariaDB on the
backend network. The board manages its own user accounts; there is no
TinyAuth or PocketID layer in front of it.

## Stack layout

```text
/opt/docker/phpbb/
├── compose.yaml
├── .ansible-build-inputs.json      build fingerprint record
├── config/
│   ├── phpbb/                      Dockerfile + scripts (build context)
│   └── nginx/phpbb.conf            origin server configuration
└── env/
    ├── phpbb.env                   application + installer environment (0600)
    └── mariadb.env                 database environment (0600)
```

Data lives in six volumes:

| Volume | Contents | Backed up by |
| --- | --- | --- |
| `phpbb-root` | Board code, `config.php`, `.phpbb-version` marker | Borg (`/phpbb-root`) |
| `phpbb-cache` | phpBB template and config cache | Rebuilt from scratch |
| `phpbb-db-data` | MariaDB data | Borg `mariadb_databases` dump hook |
| `phpbb-files` (NAS) | Attachments | NAS backup, not Borg |
| `phpbb-store` (NAS) | phpBB internal store, ACP backups | NAS backup, not Borg |
| `phpbb-ext`, `phpbb-styles`, `phpbb-avatars` (NAS) | Installed extensions, style edits, uploaded avatars | NAS backup, not Borg |

The NAS data lives under `Files/.data/PhpBB/` on the Files share; the
directories are created by the role's seed init and the volumes are declared
centrally in [storage.yml](../../group_vars/compute_servers/storage.yml).
Record what the NAS side covers in its own backup arrangements.

## Custom style (Granblue Fantasy)

The board ships a handcrafted child style of prosilver in
[files/phpbb/styles/granblue](files/phpbb/styles/granblue) — ornate navy and
gold, tiled starfield, serif headers, a marquee, and 88×31 badges. The style
is **deployment-owned**: the image bakes it into the pristine tree, the
entrypoint re-syncs it into the mounted styles volume on every start
(`phpbb_managed_styles`), and `phpbb-ensure.php` registers it in
`phpbb_styles` as a prosilver child and sets it as the board default
(`phpbb_style_set_default`), migrating users from the previous default.

To iterate on the theme: edit the files, redeploy, and the managed sync
replaces the style wholesale; phpBB recompiles its stylesheet asset when the
source files are newer. User-installed styles are data on the NFS volume and
are never touched by the sync. Because the managed style is root-owned and
read-only to the board, template editing through the ACP is unavailable for
it by design — edit in the repository instead.

Game-flavored assets under `theme/images/game/` are official Granblue
Fantasy UI sprites from the game CDN, all text-free crops: the header
band is a tab panel from `ui/tabs-sa6493bb780.png`, section title bars
and the button capsules come from `ui/button-sf56ebaca5b.png` and
`archive/parts-sfab8cdabc0.png` (sprites with baked-in labels are
rejected — buttons render through border-image with fill, so the ornate
caps stay crisp and the middle stretches), the board scroll is
`scroll_brown/bg_detail.png`, the backdrop
`sp/detail/archive/bg_picture_book.jpg`, and the ornament
`frame_flexible/base_ornament_01.png`. When iterating on the theme,
bump `assets_version` (ACP or config) alongside the edit so browsers
refetch the stylesheet.

## Crawlers

The board is public but not for AI and training-data crawlers. Two layers:

- **robots.txt** ([files/phpbb/robots.txt](files/phpbb/robots.txt)) is baked
  into the image and force-copied to the web root on every start. It allows
  Googlebot, Bingbot, and DuckDuckBot (with phpBB's recommended private-path
  disallows) and denies everyone else — compliant AI crawlers stop here.
- **nginx user-agent rule**: crawlers that ignore robots.txt (Bytespider and
  friends) get a 403 at the origin. The list lives in
  [phpbb.conf.j2](templates/nginx/phpbb.conf.j2) and mirrors the ACP's AI
  Crawlers group; extend it when phpBB ships new catalog entries.

To verify: `curl -A GPTBot https://board.fireplace.cafe/` → 403,
`curl -A Googlebot/2.1 https://board.fireplace.cafe/` → 200, and
`curl https://board.fireplace.cafe/robots.txt` → the policy above.

## How the image is built

`roles/phpbb/files/phpbb/` holds the build context:

- `Dockerfile` — pinned `php:8.4.27-fpm-alpine3.24` base, GD/intl/zip/opcache
  extensions, and the official `phpBB-3.3.19.tar.bz2` release tarball,
  verified against a SHA-256 recorded in the file. The PHP tag must stay at
  8.4.27 or newer: earlier releases are vulnerable to PHP2Shell
  (CVE-2026-109618/109619).
- `phpbb-init` — one-shot overlay. Copies the pristine tree onto the
  `phpbb-root` volume when `.phpbb-version` differs from the image's
  `PHPBB_VERSION`, excluding `config.php`, `cache`, and the mounted data
  directories. Board code stays root-owned.
- `phpbb-entrypoint` — renders PHP/FPM settings from the environment, seeds
  phpBB's guard files into the mounts, hands the writable data directories
  to the FPM user (marker-gated, with a chmod fallback for squashing NFS
  exports), runs phpBB's CLI installer once when `config.php` is empty, and
  reconciles board email settings with the environment.
- `phpbb-ensure.php`, `phpbb-health.php` — config reconciliation and the
  `/health.php` liveness endpoint (reports `ok` and, once installed,
  `db ok`).
- `phpbb-update` — one-shot maintenance command for version upgrades:
  materializes phpBB's `install/` directory from the pristine copy, runs the
  CLI database updater in `db_only` mode, then removes `install/` again so
  the board never serves with it present.

Build decisions use the repository fingerprint pattern: rebuilds happen when
the recorded fingerprint differs, the image is missing, or
`phpbb_force_rebuild=true`. The first deployment builds once.

## Vault inputs

`group_vars/phpbb/vault.yml` (see [Secrets](../../docs/secrets.md)):

| Variable | Description |
| --- | --- |
| `vault_phpbb_db_password` | MariaDB application password |
| `vault_phpbb_db_root_password` | MariaDB root password; also used by the backup dump hook |
| `vault_phpbb_admin_password` | Founder account password; phpBB allows 8–30 characters |

The generated credentials are lowercase hex. If you replace
`vault_phpbb_admin_password` with a chosen password, avoid `$`, backticks,
backslashes, and double quotes: the value travels through a shell-rendered
installer file, and those characters are rejected by the preflight
assertions.
| `vault_resend_api_key` | Resend SMTP API key; required while `phpbb_email_enabled` is true |

The founder account is `phpbb_admin_name` (default `Justin`) with
`phpbb_admin_email`. Its password is only in the vault:

```sh
ansible-vault view group_vars/phpbb/vault.yml
```

## Prerequisites

1. DNS: an A/CNAME record for `board.fireplace.cafe` pointing at the gateway.
2. Traefik: the `fireplace.cafe` DNS-challenge domain entry in the static
   configuration (already in [roles/traefik](../traefik/templates/traefik/traefik.yml.j2)).
   The Cloudflare API token in the `traefik` vault must have Zone DNS Edit
   rights for `fireplace.cafe`, or certificate issuance fails.
3. Resend: add `board.fireplace.cafe` as a sending domain (SPF/DKIM records
   from the Resend dashboard), create an SMTP API key scoped to that domain,
   and set it as `vault_resend_api_key`. phpBB authenticates as `resend` with
   that key against `smtp.resend.com:587` and sends from `phpbb_board_email`
   (default `noreply@board.fireplace.cafe`). Resend rejects envelope senders
   outside the key's domain scope, so the two must match.
4. The NFS volumes from `storage.yml` are created by the prerequisites play.

## First deploy

```sh
make deploy-prerequisites          # registers the phpbb-* NFS volumes (storage.yml)
make -C deploy check STACK=phpbb   # dry run against nuc-mini
make -C deploy phpbb               # deploy
```

On the first start the container overlays phpBB 3.3.19 onto `phpbb-root`,
waits for MariaDB, renders an installer config from the environment, runs
`install/phpbbcli.php install`, and starts PHP-FPM. The deploy task then
polls `/health.php` for `db ok`.

Verify:

```sh
docker logs phpbb          # install output; the installer config is never logged
docker ps --filter name=phpbb
curl -s https://board.fireplace.cafe/health.php   # expect: ok + db ok
```

Sign in as the founder at `/adm` with the vault password, set the board
timezone and attachment limits in the ACP, and send a test email from
ACP → System → Mass email or a password-reset to confirm Resend delivery.
Gatus watches `https://board.fireplace.cafe/` (status 200).

## Upgrading phpBB

The overlay replaces board code on the next deploy; the database updater
runs by hand afterwards.

1. Take a database dump (the nightly Borg archive has one, or run the ACP
   backup) and note the current board version from the ACP.
2. Bump `phpbb_version` in [defaults](defaults/main.yml) and the matching
   `PHPBB_VERSION`/`PHPBB_SHA256` arguments in the [Dockerfile](files/phpbb/Dockerfile).
   Verify the new tarball's SHA-256 before recording it.
3. `make -C deploy phpbb` — the fingerprint change rebuilds the image and the
   init overlay reseeds the code on the next start.
4. Run the bundled updater command from inside the container; it
   materializes `install/`, runs the CLI database updater in `db_only`
   mode, and removes `install/` again:

   ```sh
   docker compose -f /opt/docker/phpbb/compose.yaml exec phpbb phpbb-update
   ```

5. Confirm the new version in the ACP and the board's health. If the updater
   leaves `cache/install_lock` behind (interrupted run), delete it from the
   `phpbb-cache` volume; the CLI updater refuses to run while it exists.

Rollback: restore the pre-upgrade database dump, rebuild the previous
version (check out the previous defaults/Dockerfile, or set
`PHPBB_VERSION` accordingly), and redeploy. The init overlay refuses nothing
but always converges to the image's version.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `phpbb` container restart-looping | `docker logs phpbb`; installer errors print there. Missing vault inputs fail the deploy before anything starts. |
| "Delete, move or rename the install directory" banner | `install/` should never persist: the entrypoint removes it after install and `phpbb-update` removes it after updates. If it reappears after a version bump, run `phpbb-update`. |
| 403 on every route | `/install/` is closed by design; a fresh board redirects there until the CLI installer finishes. Check `docker logs phpbb`. |
| Certificate issuance fails | The `traefik` vault's Cloudflare token must cover the `fireplace.cafe` zone. |
| Uploads or avatars fail to write | NFS export squashing root: the entrypoint's chmod fallback should cover it; check `docker exec phpbb ls -ln /var/www/html/files`. |
| Email not delivered | Resend rejects envelope senders outside the key's domain scope (550 at DATA time). The sender is `phpbb_board_email`; it must live on the domain the `vault_resend_api_key` is scoped to. Check ACP → Communication → Email settings. |
| Wrong client IPs in phpBB | `phpbb_trusted_proxy_ip` must match Traefik's proxy-network address (`traefik_proxy_ipv4_address` in inventory). |
