# Petlibro

Deploys the Mosquitto broker for the feeders on `nuc-mini`. An optional catbro
container is available for protocol research. The normal control and video
service is [Kibble](../kibble/README.md).

## Default deployment

`petlibro_catbro_enabled` defaults to false. The normal stack contains
`petlibro-mosquitto`, which publishes TCP 1883 for feeder and Home Assistant
connections. MQTT access is anonymous; network access is controlled outside
the broker credentials.

Kibble owns the MQTT bridge, video service, and in-process Kalay master. This
role removes the retired `kalay-mock` systemd unit and installation when they
are present. It does not install a replacement standalone Kalay service.

## Setup

1. Configure the DNS resolver used by the feeders so `mqtt.us.petlibro.com`
   resolves to `nuc-mini`'s inventory address.
2. Deploy the broker from the repository root:

   ```sh
   make -C deploy syntax STACK=petlibro
   make -C deploy petlibro
   ```

3. Restart the feeders after changing DNS so they reconnect to the local
   broker. On `nuc-mini`, inspect connections with:

   ```sh
   docker logs --tail=100 petlibro-mosquitto
   ```

4. Configure Home Assistant's MQTT integration to use `nuc-mini` on port 1883
   without a username or password. Kibble supplies the normal feeder
   integration; verify its configuration separately.

The role does not configure the feeder DNS resolver or Home Assistant.

## Optional catbro deployment

Catbro is built on the host from `catbro_repo_url` at `catbro_repo_ref`. It is
intended for capture and protocol testing. Its published ports overlap with
Kibble's media services; resolve those conflicts before enabling it.

From the repository root:

```sh
make -C deploy deploy STACK=petlibro EXTRA_ARGS='-e petlibro_catbro_enabled=true'
```

Disable it after the capture session:

```sh
make -C deploy deploy STACK=petlibro EXTRA_ARGS='-e petlibro_catbro_enabled=false'
```

The Compose deployment uses `remove_orphans: true`, so disabling catbro removes
its container. Source, Dockerfile, or build-setting changes trigger one build
before deployment. An unchanged image is reused. Use `petlibro_force_rebuild`
to request a cached build while catbro is enabled; see
[local image builds](../../docs/operations.md#local-image-builds) for fingerprint
and retry behavior. Pin `catbro_repo_ref` for a reproducible source revision.

| Default port | Owner | Use |
| --- | --- | --- |
| TCP 1883 | Mosquitto | MQTT |
| TCP 1984 | catbro, when enabled | go2rtc API |
| TCP 8554 | catbro, when enabled | RTSP |
| TCP 8555 | catbro, when enabled | WebRTC TCP |

Kibble's Kalay master owns UDP 10001 and 10240.

## Files

Paths are relative to `/opt/docker/petlibro`:

| Path | Contents |
| --- | --- |
| `data/mosquitto/` | Broker persistence |
| `data/catbro/state.toml` | catbro feeder state, when used |
| `data/catbro/creds.toml` | Generated catbro feeder configuration |
| `src/` | catbro source checkout |

See [defaults/main.yml](defaults/main.yml) for feeder configuration and build
settings. The [historical troubleshooting notes](TROUBLESHOOTING.md) describe
the older external Kalay setup; their recovery commands are not the current
deployment procedure.
