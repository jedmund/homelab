#!/usr/bin/env bash
# Build the Kizuna walking router's Valhalla tiles from Geofabrik extracts.
# Run it on max (see "Walking router" in roles/kizuna/README.md), not on the
# Kizuna host.
#
#   router_build.sh <scratch-dir> <valhalla-image>
#
# valhalla_build_tiles reads each PBF several times, so the extracts are
# downloaded to <scratch-dir>/pbf rather than streamed, and deleted with the
# intermediate tile directory once the build succeeds. The result is
# <scratch-dir>/out/{valhalla_tiles.tar,admins.sqlite,timezones.sqlite},
# owned by the invoking user.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <scratch-dir> <valhalla-image>" >&2
  exit 64
fi

SCRATCH=$1
IMAGE=$2
EXTRACTS=${EXTRACTS:-"north-america/us asia/japan"}
THREADS=${THREADS:-32}

cd "$SCRATCH"
mkdir -p pbf work out
if [ -n "$(ls -A out)" ]; then
  echo "$SCRATCH/out is not empty; remove it first" >&2
  exit 1
fi

pbfs=()
for extract in $EXTRACTS; do
  file="pbf/$(basename "$extract")-latest.osm.pbf"
  if [ ! -s "$file" ]; then
    curl -sSfL -o "$file.part" "https://download.geofabrik.de/$extract-latest.osm.pbf"
    curl -sSfL -o "$file.md5" "https://download.geofabrik.de/$extract-latest.osm.pbf.md5"
    (cd pbf && sed "s/ .*-latest.osm.pbf/  $(basename "$file").part/" "$(basename "$file").md5" | md5sum -c --quiet)
    mv "$file.part" "$file"
  fi
  pbfs+=("/data/$file")
done

valhalla() {
  docker run --rm --user "$(id -u):$(id -g)" -v "$SCRATCH:/data" -w /data \
    "$IMAGE" "$@"
}

valhalla valhalla_build_config \
  --mjolnir-tile-dir /data/work/tiles \
  --mjolnir-tile-extract /data/out/valhalla_tiles.tar \
  --mjolnir-admin /data/out/admins.sqlite \
  --mjolnir-timezone /data/out/timezones.sqlite \
  --mjolnir-concurrency "$THREADS" >work/valhalla.json

stage() {
  echo "$(date -u +%FT%TZ) $1"
}

stage timezones
# The script downloads timezone polygons and unpacks them into its working
# directory.
valhalla bash -c 'cd /data/work && valhalla_build_timezones > /data/out/timezones.sqlite'
stage admins
valhalla valhalla_build_admins -c /data/work/valhalla.json "${pbfs[@]}"
stage tiles
valhalla valhalla_build_tiles -c /data/work/valhalla.json -j "$THREADS" "${pbfs[@]}"
stage extract
valhalla valhalla_build_extract -c /data/work/valhalla.json -v
stage finished

rm -rf work pbf
du -sh out/*
