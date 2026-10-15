# Protomaps basemap runbook

The `protomaps` role serves a Protomaps basemap archive and the matching font
and sprite assets from `nuc-mini` at `https://maps.atelier.house`. Kizuna's
MapLibre map reads them cross-origin; clients make no requests to third-party
hosts.

| Item | URL |
| --- | --- |
| Archive | `https://maps.atelier.house/basemaps/<protomaps_archive>` |
| Font and sprite base | `https://maps.atelier.house/assets/<protomaps_assets_commit>` |
| Font glyphs | `<base>/fonts/{fontstack}/{range}.pbf` |
| Sprites | `<base>/sprites/v4/light`, `<base>/sprites/v4/dark` |
| Health | `https://maps.atelier.house/healthz` |

The current values are in [defaults](defaults/main.yml): the official
`20261014` planet build (tile schema 4.15.2, for `@protomaps/basemaps` v5) and
`protomaps/basemaps-assets` commit `028c18f713baecad011301ff7a69acc39bcc2ae7`.

## Design

nginx serves files from `/srv/protomaps`, mounted read-only, behind Traefik.
nginx answers byte-range requests with `206 Partial Content`, `Content-Range`,
`Accept-Ranges: bytes`, and an ETag derived from the file's modification time
and size. Compression is disabled, and the Traefik router has no `compress`
middleware. Garage was not used: its CORS is set only through the S3
`PutBucketCors` API, it needs a public bucket and key bootstrap, and a large
archive would have to be uploaded through S3 multipart.

The route is public and unauthenticated. MapLibre fetches tiles without
credentials, so forward authentication would block every request. CORS grants
`GET` and `HEAD` to the origins in `protomaps_cors_origins` and
`protomaps_cors_origin_patterns`, allows the `Range` request header, exposes
`Content-Range`, `Content-Length`, `Accept-Ranges`, and `ETag`, and answers
`OPTIONS` preflights with `204`. Other origins receive no
`Access-Control-Allow-Origin` header.

Archive and asset paths contain the build name and assets commit, so responses
are cached as `public, max-age=31536000, immutable`. A new build or assets pin
gets a new URL. Never replace a published file in place under the same name.

`/srv/protomaps` is outside `/opt/docker` and is not backed up; every file can
be downloaded again from the pinned sources.

## First deployment

1. Create a DNS-only `A` record for `maps.atelier.house` in the Cloudflare
   `atelier.house` zone, pointing at the current home address. ddclient
   updates the record after that; it does not create missing records.
2. Deploy the role. This writes the nginx configuration, downloads and
   checksums the fonts and sprites, and stages the archive fetch script:

   ```sh
   make -C deploy protomaps
   ```

3. Download the archive on `nuc-mini`. The planet is about 139 GB. The script
   resumes a partial download when re-run, verifies the MD5 and the PMTiles
   structure, and only then renames the file into the served path:

   ```sh
   tmux new -s protomaps '/opt/docker/protomaps/fetch_archive.sh'
   ```

4. Run the checks in [Verification](#verification).

## Verification

```sh
URL=https://maps.atelier.house/basemaps/20261014.pmtiles
BASE=https://maps.atelier.house/assets/028c18f713baecad011301ff7a69acc39bcc2ae7

curl -sI -H 'Range: bytes=0-16383' "$URL"
curl -si -X OPTIONS -H 'Origin: https://kizuna.fm' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: range' "$URL"
docker run --rm protomaps/go-pmtiles:v1.31.2 show "$URL"
curl -sI -H 'Origin: https://kizuna.fm' "$BASE/fonts/Noto%20Sans%20Regular/0-255.pbf"
curl -sI -H 'Origin: https://kizuna.fm' "$BASE/sprites/v4/light.json"
```

Expect `206` with `Content-Range`, `Accept-Ranges: bytes`, and `ETag` for the
range request; `204` with `Access-Control-Allow-Origin: https://kizuna.fm` for
the preflight; the archive header, bounds, and zoom range from `pmtiles show`;
and `200` with the same CORS header for the font and sprite.

## Add a CORS origin

Exact origins go in `protomaps_cors_origins`; regular expressions go in
`protomaps_cors_origin_patterns`. The deployed list is overridden in
[group_vars/protomaps/main.yml](../../group_vars/protomaps/main.yml), which
adds the Kizuna local development servers to production:

```yaml
protomaps_cors_origins:
  - https://kizuna.fm
  - http://localhost:5176
  - http://localhost:6006
  - http://localhost:6106
```

Then run `make -C deploy protomaps`. A changed nginx configuration recreates
the container.

## Update the archive

1. Choose a build from <https://build-metadata.protomaps.dev/builds.json>.
   Upstream deletes daily builds after a few weeks.
2. Set `protomaps_build` and `protomaps_planet_md5`. The metadata lists the
   MD5 in base64; convert it to hex:

   ```sh
   echo '<md5sum value>' | base64 -d | xxd -p
   ```

3. Deploy the role, then run the fetch script on `nuc-mini` as in the first
   deployment. Deploying before the download finishes is safe; the old archive
   remains at its own URL.
4. Point the Kizuna map at the new URL. After clients have moved, delete the
   old file from `/srv/protomaps/basemaps/`. Two planet archives need about
   280 GB; check `df -h /` before downloading.

## Regional extract

Coverage is controlled by `protomaps_bbox`. Empty means the full planet. A
bbox makes the fetch script run `pmtiles extract`, which reads only the needed
byte ranges from the upstream build. Give the extract its own name so it never
shares a URL with a planet archive, and keep Shimokitazawa (139.67, 35.66)
inside every bbox:

```yaml
protomaps_bbox: "122.9,24.0,146.0,45.6"
protomaps_archive: "japan-{{ protomaps_build }}.pmtiles"
# Optional: protomaps_maxzoom: "14"
```

The equivalent manual command is:

```sh
docker run --rm -v /srv/protomaps/basemaps:/data protomaps/go-pmtiles:v1.31.2 \
  extract https://build.protomaps.com/20261014.pmtiles \
  /data/japan-20261014.pmtiles --bbox=122.9,24.0,146.0,45.6
```

## Update fonts and sprites

Set `protomaps_assets_commit` to a new `protomaps/basemaps-assets` commit and
`protomaps_assets_sha256` to the SHA-256 of
`https://codeload.github.com/protomaps/basemaps-assets/tar.gz/<commit>`. Keep
`sprites/v4` while the client uses `@protomaps/basemaps` v5. Deploy, move the
client to the new base URL, then remove the old directory under
`/srv/protomaps/assets/` and its tarball under `/srv/protomaps/downloads/`.
