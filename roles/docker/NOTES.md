# docker role notes

## NFS boot race and current mitigation

On reboot, docker starts its container-restore phase before routing to the NAS is stable, and ~20% of containers with NFS-backed volumes exit with `network is unreachable`. Docker does not retry start-time mount failures, so they sit exited until something kicks them.

Current mitigation (implemented here, in this role):

1. `nas-reachable.service` — oneshot that TCP-probes `{{ nas_server }}:2049` for up to 120s before declaring the NAS reachable.
2. `docker.service.d/10-wait-for-nas.conf` drop-in — orders docker `After=/Wants=nas-reachable.service`.
3. `docker-stacks-up.service` — oneshot that runs `docker compose up -d` across every `/opt/docker/*/compose.yaml` ~10s after docker is up. This is the belt-and-suspenders step that actually catches the race: steps 1 and 2 help but the race is *within* docker's own restore sweep (bridge/nftables setup briefly disrupts routing) and TCP reachability alone isn't enough to prevent it.

## Alternative we deliberately didn't take: host-level NFS mounts

We considered migrating from docker-managed NFS volumes (`driver: local`, `driver_opts: type=nfs`) to host-level systemd `.mount` units with bind mounts in compose. This would be the architectural root-cause fix — docker would never touch NFS at all.

We chose not to do this because:

- **Blast radius of a NAS outage becomes host-wide**. Today `hard,intr` NFS failures are isolated per-container. With host-level hard mounts, any process touching `/mnt/nas/*` hangs indefinitely if the NAS goes down — including shell tab-completion, monitoring agents, backup scripts. Today only the container stacks hang.
- **Big migration diff** with silent-failure risk. ~30 mount units + 50+ volume references across 11 compose files. If one reference is missed, systemd auto-creates an empty `/mnt/nas/xxx` dir and the container writes to the wrong place without erroring.
- **Shutdown ordering gets sensitive** — systemd must unmount NFS before networking tears down or shutdown hangs 90s on stuck unmounts.
- **`.mount` units lack proper `Restart=`** — transient NAS unreachability at boot needs a watchdog layered on top.
- **Applies to all compute hosts in lockstep** — can't stage per-host.
- **Mount unit filenames must exactly match paths**, so any rename elsewhere breaks silently.

If `docker-stacks-up.service` stops being sufficient — e.g., if stacks fail in ways that `docker compose up -d` can't recover, or if the kick window grows unreliable — revisit this migration. Scope: replace `nfs_volumes` in `group_vars/compute_servers/storage.yml` with host mount definitions, generate a systemd `.mount` unit per share, and convert every compose file's NFS volume references to bind mounts against `/mnt/nas/<share>`.
