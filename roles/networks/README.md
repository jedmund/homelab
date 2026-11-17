# Networks

The `networks` role creates the shared Docker bridge networks on every Linux
compute host: `proxy-network`, `backend-internal`, `shared-network`,
`cibuild-network`, and `vpn-network`, plus the Minecraft networks on assigned
hosts. It runs from [prerequisites.yml](../../deploy/prerequisites.yml) and
[minecraft.yml](../../deploy/minecraft.yml). See
[Conventions: Networks and routing](../../CONVENTIONS.md#networks-and-routing)
for which network a service joins.

## Proxy network address plan

Traefik on `nuc-mini` has a static `proxy-network` address,
`traefik_proxy_ipv4_address`. Stereo and phpBB trust only that address. Without
a reserved range, Docker can give that address to any container that starts
before Traefik, for example while containers restart during a Docker upgrade.
Traefik then fails with `failed to set up container networking: Address
already in use`, and every routed service is unreachable.

`proxy_network_ipam` in [inventory](../../inventory/hosts.yml) fixes the
subnet and gateway and limits dynamic addresses to `iprange`. Static addresses
must be inside the subnet and outside `iprange`;
[tests/test_networks.py](../../tests/test_networks.py) checks this for every
host that sets the plan.

Docker cannot change a network's IPAM settings in place. When the plan differs
from the live network, `community.docker.docker_network` would detach every
container and recreate the network without reattaching them. The role
therefore never passes a plan the live network does not already match:

| Live network | Behavior |
| --- | --- |
| Absent | Created with the plan |
| Matches the plan | Left unchanged |
| Differs, default run | Left unchanged; the run prints a warning |
| Differs, `networks_recreate_proxy=true` | Recreated by `files/recreate_network.py`, containers reattached |

Check mode never recreates the network.

## Recreating the proxy network

Recreation detaches and reattaches every container on `proxy-network`. All
routed services are unreachable for that period, normally under a minute. It
covers containers from every source, including Komodo stacks under
`/etc/komodo/stacks`, without recreating them.

The script:

1. Records every container on the network, running or stopped, with its
   address, aliases, and gateway priority in
   `/var/backups/docker-networks/proxy-network-<timestamp>.json` (mode `0600`,
   `networks_snapshot_dir`), and prints the path before changing anything.
2. Disconnects them, removes the network, and creates it with the plan, keeping
   the driver, options, and labels. If a disconnect or the removal fails, it
   reattaches the containers to the unchanged network and stops. If creation
   fails, it recreates the network with the original IPAM settings.
3. Reattaches each container, statically pinned containers first. A container
   keeps its previous address when that address is outside the new `iprange`,
   so Traefik backends and proxies that cached a peer address (such as
   `phpbb-nginx`) stay valid. Addresses inside the range are reassigned.
4. Restarts the containers in `networks_proxy_restart` (default `traefik`) so
   Traefik re-reads container addresses.

Stopped containers must be reattached: they store the network ID and fail to
start with `network ... not found` after it is removed. A kept address is
stored on the endpoint as a static address. Compose does not treat this as
drift; the container moves into the dynamic range when its stack next
recreates it.

Run it only in an authorized window, from the main checkout (not a worktree):

```sh
make -C deploy deploy STACK=prerequisites \
  EXTRA_ARGS="--limit nuc-mini --tags networks -e networks_recreate_proxy=true"
```

Afterwards, verify on the host:

```sh
docker network inspect proxy-network --format '{{json .IPAM.Config}}'
docker inspect traefik --format '{{(index .NetworkSettings.Networks "proxy-network").IPAddress}}'
docker ps -a --filter status=restarting --filter status=exited
```

Expect the plan's `IPRange`, Traefik on `traefik_proxy_ipv4_address`, and no
new failed containers. Then check routed services through Traefik.

If the script exits non-zero, it prints the snapshot path and each container
it could not reconnect. Reconnect those by hand from the snapshot entry:

```sh
docker network connect [--ip <ipv4_address>] --alias <alias> ... proxy-network <container>
```

Redeploying a container's stack also reattaches it.
