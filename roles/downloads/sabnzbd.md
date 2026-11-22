# SABnzbd

Usenet download client at `sab.atelier.house`, running on nuc-mini. Sonarr,
Radarr, and Lidarr send NZBs to it; Prowlarr supplies the indexers. The Usenet
provider is Newshosting.

SABnzbd is deployed by the [downloads](README.md) role and runs in gluetun's
network namespace, so its traffic leaves through ProtonVPN. gluetun publishes
host port 8085 and carries the `sabnzbd` alias on the shared network. Its data
stays in `/opt/docker/sabnzbd`.

## Layout

| Path | Container path | Contents |
| --- | --- | --- |
| `/opt/docker/sabnzbd/config` | `/config` | `sabnzbd.ini`, queue, and history database |
| `/opt/docker/sabnzbd/incomplete` | `/incomplete` | In-progress jobs, repaired and extracted on local disk |
| `downloads` volume (Ingest NFS share) | `/downloads` | Completed jobs under `/downloads/usenet/complete/<category>` |

The Starr apps mount the same `downloads` volume at `/downloads`, so no remote
path mapping is needed. Incomplete jobs stay off the NFS share because par2
repair and unrar are slow over NFS, and because Unpackerr's folder watcher
covers `/downloads`.

SABnzbd repairs and extracts its own jobs and deletes the archives after a
successful unpack. Unpackerr's Starr integration handles only torrent queue
items by default, so it skips SABnzbd jobs. Its folder watcher on `/downloads`
(`UN_FOLDER_0_*`, with `DELETE_AFTER=10m`) also covers `/downloads/usenet`.
Whether it acts on a completed job that still contains archives, for example
after a failed unpack, has not been verified.

The whole route, including `/api`, is behind TinyAuth. The Starr apps connect
directly over the shared Docker network as `http://sabnzbd:8080` and do not use
the Traefik route. SABnzbd's host whitelist (`sabnzbd_host_whitelist`) must
include both `sab.atelier.house` and the container name `sabnzbd`; requests
with any other hostname receive `403 Hostname verification failed`.

## Initial configuration

The downloads role seeds `config/sabnzbd.ini` only when it is absent. The seed sets the
host whitelist (`sabnzbd_host_whitelist`), the incomplete and complete folders, and the
`movies`, `tv`, and `music` categories. SABnzbd generates its API and NZB keys
on first start and owns the file afterward. Changing these defaults does not
modify an existing configuration; edit it in the web UI.

Deploy `downloads`, then `traefik` and `tinyauth` for the
`sab.atelier.house` route and access label, and `backup` for the history
dump and the `incomplete/` exclusion:

```bash
make -C deploy downloads
make -C deploy traefik
make -C deploy tinyauth
make -C deploy backup
```

After the first deployment:

1. Open `https://sab.atelier.house`. The setup wizard runs because no server is
   configured.
2. Add the Newshosting server: host `news.newshosting.com`, port `563`, SSL
   enabled, 20 to 30 connections, and the Newshosting username and password.
   Run the wizard's server test.
3. Confirm Config > Folders shows `/incomplete` and
   `/downloads/usenet/complete`, and Config > Categories lists `movies`, `tv`,
   and `music`.
4. Set a username and password in Config > General. SABnzbd treats requests
   from private addresses as local, so without a login the published port
   (`http://<nuc-mini>:8085`) gives the full UI to the LAN without TinyAuth.
   The Starr apps use the API key and are unaffected.
5. Copy the API key from Config > General.

Then connect the other applications:

1. Prowlarr: add the Usenet indexers and sync them to Sonarr, Radarr, and
   Lidarr.
2. Sonarr, Radarr, and Lidarr: add a SABnzbd download client with host
   `sabnzbd`, port `8080`, the API key, and the `tv`, `movies`, or `music`
   category.
3. Optionally add a delay profile in Sonarr and Radarr that prefers Usenet.

The Newshosting credentials and the API keys are entered in the web UI and
stored in `sabnzbd.ini`, which is covered by the `/opt/docker` backup. The downloads
role does not read them from the Ansible vault.

## Verification

```bash
ssh nuc 'docker inspect sabnzbd --format "{{.State.Health.Status}}"'
ssh nuc 'curl -fsS "http://localhost:8085/api?mode=version"'
```

The first command prints `healthy`. The second prints the SABnzbd version. Then
send a test search from Sonarr or Radarr and confirm the job completes and is
imported.

## Updates and rollback

`sabnzbd_image` uses the floating `latest` tag, like the other linuxserver
media images. A deploy with the shared `always` pull policy updates it. To roll
back, set `sabnzbd_image` to a previous `lscr.io/linuxserver/sabnzbd` version
tag and redeploy. SABnzbd refuses to load a `sabnzbd.ini` written by a newer
configuration version, so restore `config/` from backup when rolling back
across a configuration version change.

## Backups

The nightly SQLite dump includes `config/admin/history1.db`. The rest of
`config/` is copied live. `incomplete/` is excluded. Completed downloads on the
Ingest share are not backed up by the downloads role.
