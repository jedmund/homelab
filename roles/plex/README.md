# Plex

Plex Media Server on nuc-mini, in the `plex` Compose stack at
`/opt/docker/plex`. Plex's data directory is
`/opt/docker/plex/config/Library/Application Support/Plex Media Server`.

`plex_image` is a floating tag. The Komodo `update-plex` Action applies new
images daily; the rollback is in [defaults](defaults/main.yml).

## Anime library plugins

The Anime library uses two third-party components that the role installs at
pinned upstream commits:

| Component | Installed at | Version variables |
| --- | --- | --- |
| [HAMA](https://github.com/ZeroQI/Hama.bundle) metadata agent | `Plug-ins/Hama.bundle` | `plex_hama_commit`, `plex_hama_archive_checksum` |
| [Absolute Series Scanner](https://github.com/ZeroQI/Absolute-Series-Scanner) | `Scanners/Series/Absolute Series Scanner.py` | `plex_ass_commit`, `plex_ass_checksum` |

The HAMA archive is downloaded to `/opt/docker/plex/plugins` and extracted
into the bundle. `Hama.bundle/.homelab-commit` records the installed commit.
When it differs from `plex_hama_commit`, or is missing, the role deletes the
bundle and extracts it again. HAMA keeps its caches and logs in
`Plug-in Support/Data/com.plexapp.agents.hama`, outside the bundle, so
replacing the bundle does not affect them. Existing matches are stored by ID
and are kept.

Plex loads plugins and scanners only when it starts. A deployment that
installs a new version recreates the container, which interrupts playback.

HAMA versions before upstream commit `ae7fdee` (2026-10-03) cannot match series
folders that contain seasons other than 1, such as `Season 1` and `Season 2`.
For those folders HAMA searches only TheTVDB, and TheTVDB no longer supports
title search on the APIs HAMA uses. Newer versions search AniDB titles and map
the result to the TheTVDB series. With any version, a series can be matched
manually by entering its TheTVDB ID (for example `371310`) in Fix Match.

Do not pin HAMA at or after upstream commit `570c860` (2026-10-03) until a
release supplies TheTVDB v4 credentials. From that commit, search and metadata
use TheTVDB's v4 API with a placeholder API key (`TVDB_API_KEY = 'TODO'`). The
v4 login returns 401, so search returns no results and series matched to
TheTVDB receive no TheTVDB metadata. `ae7fdee` is the search fix on the v2
API, which still works for metadata.

### Update or roll back

1. Choose the upstream commit and read the commits since the current pin,
   including which TheTVDB module `Contents/Code/__init__.py` imports.
2. Compute the checksums:

   ```sh
   curl -fsSL https://github.com/ZeroQI/Hama.bundle/archive/<commit>.tar.gz | shasum -a 256
   curl -fsSL "https://raw.githubusercontent.com/ZeroQI/Absolute-Series-Scanner/<commit>/Scanners/Series/Absolute%20Series%20Scanner.py" | shasum -a 256
   ```

3. Set the commit and `sha256:<checksum>` variables in
   [defaults](defaults/main.yml), then deploy:

   ```sh
   make -C deploy check STACK=plex
   make -C deploy plex
   ```

To roll back, set the previous commit and checksum values and deploy.

## Verification

```sh
ssh nuc 'cat "/opt/docker/plex/config/Library/Application Support/Plex Media Server/Plug-ins/Hama.bundle/.homelab-commit"'
ssh nuc 'docker logs --since 10m plex 2>&1 | tail -5; docker inspect plex --format "{{.State.Status}} {{.State.StartedAt}}"'
ssh nuc 'tail -5 "/opt/docker/plex/config/Library/Application Support/Plex Media Server/Logs/PMS Plugin Logs/com.plexapp.agents.hama.log"'
```

The marker names `plex_hama_commit`, the container is running, and the HAMA
log shows the agent starting and loading `anime-titles.xml`. In Plex, Fix Match
on an Anime series returns results.

## Stuck library scans

A library scan request can return success without scanning. The server log then
reports `Library Updater: Section <n> is already being updated.` for each
request, and `ps` in the container lists defunct (`Z`) Plex processes:

```sh
ssh nuc "docker exec plex ps -eo pid,stat,etime,comm | awk '\$2 ~ /Z/'"
```

This was seen on 2026-11-23 with PMS 1.43.5.11079: the server stopped
collecting finished child processes after a scan, and every library stayed
queued behind it. Restarting the container (`docker restart plex`) cleared it.
The cause was not established; a credits detection job failed at the same time.
