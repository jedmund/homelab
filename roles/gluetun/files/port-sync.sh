#!/bin/sh
# Sets qBittorrent's listening port to the port gluetun forwards for it.
# gluetun lists its forwarded ports in ascending order; qBittorrent uses the
# one at QBITTORRENT_PORT_INDEX (zero-based). The container is healthy only
# while the two match.
set -u

marker=/tmp/in-sync
field=$((QBITTORRENT_PORT_INDEX + 1))

while :; do
  ports=$(curl -fsS -m 5 -H "X-API-Key: ${GLUETUN_API_KEY}" "${GLUETUN_URL}/v1/portforward" |
    tr -d ' \n' | sed -n 's/.*"ports":\[\([0-9,]*\)\].*/\1/p')
  port=$(printf '%s\n' "${ports}" | awk -F, -v field="${field}" '{ print $field }')
  current=$(curl -fsS -m 5 "${QBITTORRENT_URL}/api/v2/app/preferences" |
    tr -d ' \n' | sed -n 's/.*"listen_port":\([0-9]*\).*/\1/p')

  if [ -z "${port}" ]; then
    echo "no forwarded port at index ${QBITTORRENT_PORT_INDEX} (forwarded: ${ports:-none})"
    rm -f "${marker}"
  elif [ -z "${current}" ]; then
    echo "cannot read qBittorrent preferences; is localhost authentication bypassed?"
    rm -f "${marker}"
  elif [ "${current}" = "${port}" ]; then
    touch "${marker}"
  elif curl -fsS -m 5 -o /dev/null \
    --data-urlencode "json={\"listen_port\":${port},\"random_port\":false,\"upnp\":false}" \
    "${QBITTORRENT_URL}/api/v2/app/setPreferences"; then
    echo "listening port changed from ${current} to ${port}"
    touch "${marker}"
  else
    echo "failed to set listening port ${port}"
    rm -f "${marker}"
  fi

  sleep "${PORT_SYNC_INTERVAL}"
done
