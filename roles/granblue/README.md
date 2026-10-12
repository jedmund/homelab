# Granblue

Jobs for [granblue.team](https://granblue.team) that talk to Granblue Fantasy.
The stack runs its own gluetun container on ProtonVPN, and every other service
shares its network namespace, so game traffic only leaves through the tunnel.
It is separate from the media [gluetun](../gluetun/) stack.

| Service | Container | Purpose |
| --- | --- | --- |
| `gluetun` | `granblue-gluetun` | ProtonVPN over WireGuard |
| `gacha-rates` | `granblue-gacha-rates` | Reads the game's current draw banner and its published rates, and sends them to the granblue.team API |

## Gacha rates

`gacha-rates` runs `script/fetch_gacha_rates.rb` from
[hensei-api](https://github.com/jedmund/hensei-api) on `ruby:3.4.4-slim`. It
runs once when the container starts, then at five minutes past each hour.
Banners change on the hour at 19:00 JST. A run that finds the banner it last
uploaded does nothing.

The script is downloaded at the commit in
`granblue_gacha_rates_script_commit` and checked against
`granblue_gacha_rates_script_checksum`. To update it, change both in
[defaults](defaults/main.yml). The checksum is the SHA-256 of the file at that
commit:

```sh
curl -sfL https://raw.githubusercontent.com/jedmund/hensei-api/<commit>/script/fetch_gacha_rates.rb | shasum -a 256
```

The script signs in with a game account's cookies, kept in
`/opt/docker/granblue/gacha-rates/data/gbf-cookies.json` and refreshed from the
game's responses. `gbf-cookies-state.json` beside it records the last uploaded
banner. Neither is backed up: if they're lost, seed the cookies again.

## Prerequisites

1. In the Proton account, create a WireGuard configuration (VPN → WireGuard
   configuration, platform GNU/Linux, NAT-PMP off). The stack's configuration
   is named `nuc-gluetun-granblue`. Only its `[Interface]` values are used:
   `PrivateKey` goes in the vault, and `Address` must be `10.2.0.2/32`.
   gluetun chooses its own servers, so the `[Peer]` section is ignored.
2. Create `group_vars/granblue/vault.yml` with the inputs in
   [Secrets](../../docs/secrets.md#groupvarsgranbluevaultyml).
3. On a free Proton plan, set `granblue_vpn_free_only: true`; free servers
   are limited to a few countries, so `granblue_vpn_server_countries` may
   also need changing.

## First deployment

```sh
make -C deploy check STACK=granblue
make -C deploy granblue
```

Confirm the tunnel and its exit address. The address should belong to Proton,
not the home connection:

```sh
ssh nuc 'docker inspect granblue-gluetun --format "{{.State.Health.Status}}"'
ssh nuc 'docker exec granblue-gluetun wget -qO- https://ipinfo.io/json'
```

The first `gacha-rates` run fails until the cookies are seeded.

## Seed the game account's cookies

Sign the game account in to the game in a browser, copy the `Cookie` request
header of any `game.granbluefantasy.jp` request from the Network panel, and
run on the control machine:

```sh
pbpaste | ssh nuc 'docker exec -i granblue-gacha-rates ruby /app/fetch_gacha_rates.rb --import-cookies'
ssh nuc 'docker restart granblue-gacha-rates'
```

Moving an existing session from another machine instead: stop the job there
first, so two machines don't refresh one session, then copy its
`gbf-cookies.json` and `gbf-cookies-state.json` into the data directory with
owner `granblue_gacha_rates_uid` and mode `0600`.

## Verification

```sh
ssh nuc 'docker logs --tail 20 granblue-gacha-rates'
curl -s 'https://api.granblue.team/v1/gacha/catalogue?mode=current' | jq .banner
```

A working run logs `Uploaded banner <id>` or `Banner <id> is unchanged`, and
the API's banner has a recent `fetched_at`.

## Failures

| Log | Meaning | Action |
| --- | --- | --- |
| `The spare account is signed out of the game` | The session expired or was rejected | Seed the cookies again |
| `Set GBF_UID` or `Set GACHA_RATES_URL and GACHA_RATES_TOKEN` | Missing vault input | Fix the vault and redeploy |
| `The API returned 422` | The API rejected the game's response | Check the hensei-api logs; the game's format may have changed |
| No output and `gacha-rates` not running | gluetun is unhealthy | Check `docker logs granblue-gluetun` |

With `vault_granblue_gacha_rates_alert_webhook` set, each failure is also posted
to Discord.
