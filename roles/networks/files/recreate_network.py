#!/usr/bin/env python3
"""Recreate a Docker bridge network with a new IPAM plan and reattach containers.

Docker cannot change a network's IPAM configuration in place. This script
records every container endpoint on the network, running or stopped, writes
that record to a snapshot file, recreates the network, and reconnects each
container with its aliases and gateway priority.

Each container keeps its previous address when that address is outside the new
dynamic range, so peers that cached it (Traefik backends, nginx upstreams) stay
valid. Such an address is stored as a static address on the endpoint until the
container is next recreated. Addresses inside the new range are reassigned
dynamically. Containers with a pinned address are reconnected first.

Stopped containers must be reattached too: they store the network ID and fail
to start once the network they reference is removed.

Prints "unchanged" when the network already matches, otherwise "recreated".
Exits non-zero if any container could not be reattached; the snapshot file
lists the endpoints for manual recovery.
"""

import argparse
import ipaddress
import json
import os
import subprocess
import sys
import time


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)}: {result.stderr.strip()}")
    return result


def inspect_network(name):
    result = docker("network", "inspect", name, check=False)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


def matches(network, subnet, gateway, ip_range):
    configs = ((network or {}).get("IPAM") or {}).get("Config") or []
    return (
        len(configs) == 1
        and configs[0].get("Subnet") == subnet
        and configs[0].get("Gateway") == gateway
        and configs[0].get("IPRange") == ip_range
    )


def endpoints(network, ip_range):
    """Record every container endpoint on the network, including stopped ones."""
    pool = ipaddress.ip_network(ip_range)
    ids = set(docker("ps", "-aq", "--no-trunc", "--filter", f"network={network['Id']}").stdout.split())
    ids.update((network.get("Containers") or {}).keys())
    records = []
    for container_id in sorted(ids):
        result = docker("inspect", container_id, check=False)
        if result.returncode != 0:
            continue  # removed since listing
        container = json.loads(result.stdout)[0]
        settings = container["NetworkSettings"]["Networks"].get(network["Name"])
        if settings is None:
            continue
        pinned = (settings.get("IPAMConfig") or {}).get("IPv4Address") or ""
        previous = settings.get("IPAddress") or ""
        keep = pinned or (previous if previous and ipaddress.ip_address(previous) not in pool else "")
        short_id = container["Id"][:12]
        records.append({
            "container": container["Name"].lstrip("/"),
            "id": container["Id"],
            "running": container["State"].get("Running", False),
            "pinned_ipv4_address": pinned,
            "previous_ipv4_address": previous,
            "ipv4_address": keep,
            "aliases": [a for a in settings.get("Aliases") or [] if a != short_id],
            "gw_priority": settings.get("GwPriority") or 0,
        })
    records.sort(key=lambda r: (r["pinned_ipv4_address"] == "", r["ipv4_address"] == "", r["container"]))
    return records


def create(network, subnet, gateway, ip_range):
    args = ["network", "create", "--driver", network.get("Driver") or "bridge"]
    if subnet:
        args += ["--subnet", subnet]
    if gateway:
        args += ["--gateway", gateway]
    if ip_range:
        args += ["--ip-range", ip_range]
    if network.get("Internal"):
        args.append("--internal")
    if network.get("Attachable"):
        args.append("--attachable")
    for key, value in sorted((network.get("Options") or {}).items()):
        args += ["--opt", f"{key}={value}"]
    for key, value in sorted((network.get("Labels") or {}).items()):
        args += ["--label", f"{key}={value}"]
    docker(*args, network["Name"])


def connect(name, record):
    args = ["network", "connect"]
    if record["ipv4_address"]:
        args += ["--ip", record["ipv4_address"]]
    for alias in record["aliases"]:
        args += ["--alias", alias]
    if record["gw_priority"]:
        args += ["--gw-priority", str(record["gw_priority"])]
    return docker(*args, name, record["id"], check=False)


def reattach(name, records):
    failed = []
    for record in records:
        result = connect(name, record)
        if result.returncode != 0 and "already exists" not in result.stderr:
            failed.append(f"{record['container']}: {result.stderr.strip()}")
    return failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--subnet", required=True)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--ip-range", required=True)
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--restart", action="append", default=[],
                        help="container to restart after reattachment, if present")
    opts = parser.parse_args()

    network = inspect_network(opts.name)
    if network is None:
        sys.exit(f"network {opts.name} does not exist; let the networks role create it")
    if matches(network, opts.subnet, opts.gateway, opts.ip_range):
        print("unchanged")
        return

    records = endpoints(network, opts.ip_range)
    os.makedirs(opts.snapshot_dir, mode=0o700, exist_ok=True)
    snapshot = os.path.join(
        opts.snapshot_dir, f"{opts.name}-{time.strftime('%Y%m%dT%H%M%S')}.json"
    )
    with open(os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
        json.dump({"network": network, "endpoints": records}, handle, indent=2)
    print(f"snapshot: {snapshot}", file=sys.stderr, flush=True)

    detached = []
    for record in records:
        result = docker("network", "disconnect", "--force", opts.name, record["id"], check=False)
        if result.returncode == 0 or "is not connected" in result.stderr:
            detached.append(record)
        elif docker("inspect", record["id"], check=False).returncode != 0:
            continue  # removed since listing
        else:
            failed = reattach(opts.name, detached)
            sys.exit(f"disconnect failed for {record['container']}: {result.stderr.strip()}; "
                     f"network left in place, {len(detached) - len(failed)} reattached, failures: {failed}")

    removed = docker("network", "rm", opts.name, check=False)
    if removed.returncode != 0:
        failed = reattach(opts.name, detached)
        sys.exit(f"network rm failed: {removed.stderr.strip()}; original network kept, "
                 f"reattach failures: {failed}")

    error = None
    try:
        create(network, opts.subnet, opts.gateway, opts.ip_range)
    except RuntimeError as exc:
        # Put the original network back so containers can still be reattached.
        error = exc
        old = ((network.get("IPAM") or {}).get("Config") or [{}])[0]
        create(network, old.get("Subnet"), old.get("Gateway"), old.get("IPRange"))

    failed = reattach(opts.name, detached)
    for name in opts.restart:
        if docker("inspect", name, check=False).returncode == 0:
            result = docker("restart", name, check=False)
            if result.returncode != 0:
                failed.append(f"{name}: restart: {result.stderr.strip()}")

    if error or failed or not matches(inspect_network(opts.name), opts.subnet, opts.gateway, opts.ip_range):
        if error:
            print(f"create failed, restored original IPAM: {error}", file=sys.stderr)
        for line in failed:
            print(f"reattach failed: {line}", file=sys.stderr)
        sys.exit(1)
    print("recreated")
    print(f"reattached: {len(detached)}")


if __name__ == "__main__":
    main()
