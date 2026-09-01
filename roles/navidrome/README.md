# Navidrome (temporary)

This role deploys a pinned Navidrome instance on `nuc-mini` for temporary
OpenSubsonic compatibility testing. It is intentionally excluded from
`deploy/all.yml` and uses Navidrome's local accounts rather than TinyAuth or
OIDC.

## Deploy

Deploy the Cloudflare DNS record, then the standalone stack:

```sh
make deploy-ddclient
make deploy-navidrome
```

Open <https://music.atelier.house> from the `192.168.1.0/24` LAN and create the
initial local administrator. The LAN restriction protects the first-run admin
claim page; adjust `navidrome_allowed_cidrs` only if a test client genuinely
needs to connect through the public route from another network.

Containers attached to `shared-network` can bypass Traefik and reach the API at
`http://navidrome:4533`. Navidrome reads the existing external `music` volume
at `/music` read-only and stores its database and cache under
`/opt/docker/navidrome/data`.

## Verify OpenSubsonic

After creating a user, verify the server's advertised OpenSubsonic extensions
with salted token authentication:

```sh
export NAVIDROME_USER='<user>'
export NAVIDROME_PASSWORD='<password>'
salt="$(openssl rand -hex 8)"
token="$(printf '%s%s' "$NAVIDROME_PASSWORD" "$salt" | md5)"

curl --fail --silent --show-error --get \
  'https://music.atelier.house/rest/getOpenSubsonicExtensions.view' \
  --data-urlencode "u=$NAVIDROME_USER" \
  --data-urlencode "t=$token" \
  --data-urlencode "s=$salt" \
  --data-urlencode 'v=1.16.1' \
  --data-urlencode 'c=opensubsonic-check' \
  --data-urlencode 'f=json' | jq
```

The container health check and Traefik service health check both use the
unauthenticated `/ping` endpoint.

## Tear down

Stop and remove the temporary containers and network while retaining the data
directory for a reversible redeploy:

```sh
ssh nuc-mini 'cd /opt/docker/navidrome && docker compose down'
```

After the evaluation, remove the role, playbook, inventory group, Make target,
DNS entry, and `deploy-all-exclude` annotation in one cleanup change. Delete
`/opt/docker/navidrome` separately only when its local database is no longer
needed.
