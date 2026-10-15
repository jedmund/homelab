#!/usr/bin/env bash
# Build the Kizuna geocoder's Photon database from the worldwide Photon JSON
# dump, keeping only the countries in COUNTRY_CODES. Run it on max (see
# "Geocoder" in roles/kizuna/README.md), not on the Kizuna host.
#
#   geocoder_import.sh <scratch-dir> <photon-image>
#
# The dump is fetched in ordered 256 MiB range chunks, several at a time,
# because a single connection to the download server is slow. The import
# consumes and deletes each chunk in order, so the full dump is never stored.
# Lines for other countries are dropped with grep before Photon parses them;
# Photon's -country-codes filter still applies to what remains. The database
# is written to <scratch-dir>/data/photon_data, owned by UID/GID 9011.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <scratch-dir> <photon-image>" >&2
  exit 64
fi

SCRATCH=$1
IMAGE=$2
URL=${DUMP_URL:-https://download1.graphhopper.com/public/photon-dump-planet-1.0-latest.jsonl.zst}
COUNTRY_CODES=${COUNTRY_CODES:-us,jp}
LANGUAGES=${LANGUAGES:-en,ja}
PARALLEL=${PARALLEL:-8}
HEAP=${HEAP:-24g}
THREADS=${THREADS:-16}
CHUNK=$((256 * 1024 * 1024))

if [ -e "$SCRATCH/data/photon_data" ]; then
  echo "$SCRATCH/data/photon_data already exists; remove it first" >&2
  exit 1
fi
mkdir -p "$SCRATCH/chunks" "$SCRATCH/data"
sudo chown 9011:9011 "$SCRATCH/data"
cd "$SCRATCH"

headers=$(curl -sSfI "$URL" | tr -d '\r')
size=$(awk -F': ' 'tolower($1) == "content-length" { print $2 }' <<<"$headers")
etag=$(awk -F': ' 'tolower($1) == "etag" { print $2 }' <<<"$headers")
count=$(((size + CHUNK - 1) / CHUNK))
echo "dump: $URL size=$size etag=$etag chunks=$count"

# If-Match makes a chunk fail rather than mix two dump versions when upstream
# replaces the file mid-download.
fetch_chunk() {
  local i=$1 start end
  start=$((i * CHUNK))
  end=$((start + CHUNK - 1))
  curl -sSf --retry 5 --retry-all-errors -H "If-Match: $etag" \
    -r "$start-$end" -o "chunks/$i.part" "$URL"
  mv "chunks/$i.part" "chunks/$i"
}
export -f fetch_chunk
export URL CHUNK etag

stream_chunks() {
  local i
  for ((i = 0; i < count; i++)); do
    until [ -f "chunks/$i" ]; do
      kill -0 "$fetch_pid" 2>/dev/null || [ -f "chunks/$i" ] || {
        echo "chunk $i was not fetched" >&2
        return 1
      }
      sleep 1
    done
    cat "chunks/$i"
    rm -f "chunks/$i"
  done
}

seq 0 $((count - 1)) | xargs -P "$PARALLEL" -I{} bash -c 'fetch_chunk {}' &
fetch_pid=$!

# The country prefilter keeps the header and CountryInfo objects and any line
# that names one of the countries. It must match COUNTRY_CODES.
pattern=$(tr ',' '|' <<<"$COUNTRY_CODES")
set +e
stream_chunks | zstd -dc |
  LC_ALL=C grep -E "\"country_code\":\"($pattern)\"|^ ?\{\"type\":\"(NominatimDumpFile|CountryInfo)\"" |
  docker run -i --rm --name kizuna-geocoder-import --user 9011:9011 \
    -w /photon/data -v "$SCRATCH/data:/photon/data" --entrypoint java "$IMAGE" \
    "-Xms$HEAP" "-Xmx$HEAP" -jar /photon/photon.jar import -import-file - \
    -j "$THREADS" -country-codes "$COUNTRY_CODES" -languages "$LANGUAGES" \
    -data-dir /photon/data
statuses=("${PIPESTATUS[@]}")
wait "$fetch_pid"
fetch_status=$?
set -e

echo "pipeline exit statuses: ${statuses[*]} fetch: $fetch_status"
for status in "${statuses[@]}" "$fetch_status"; do
  if [ "$status" -ne 0 ]; then
    echo "import incomplete; discard $SCRATCH/data and run again" >&2
    exit 1
  fi
done
sudo du -sh "$SCRATCH/data/photon_data"
