#!/usr/bin/env python3
"""Provision only the dedicated logging bucket and its pre-existing vault key."""
from pathlib import Path
import subprocess
import sys
import time


def garage(*args, required=True):
    result = subprocess.run(['docker', 'exec', 'logging-garage', '/garage', *args],
                            text=True, capture_output=True, check=False)
    if required and result.returncode:
        raise RuntimeError('Garage provisioning command failed: ' + args[0])
    return result


def main():
    values = dict(line.split('=', 1) for line in Path(sys.argv[1]).read_text().splitlines()
                  if line and not line.startswith('#'))
    for _ in range(30):
        if garage('status', required=False).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Garage did not become ready')
    changed = False
    if 'No nodes currently have a role' in garage('layout', 'show').stdout:
        node = garage('node', 'id', '-q').stdout.strip().split('@')[0]
        garage('layout', 'assign', '-z', 'homelab', '-c', '1T', node)
        garage('layout', 'apply', '--version', '1')
        changed = True
    bucket = values['LOKI_S3_BUCKET']
    if garage('bucket', 'info', bucket, required=False).returncode:
        garage('bucket', 'create', bucket)
        changed = True
    key = values['LOKI_S3_ACCESS_KEY']
    if garage('key', 'info', key, required=False).returncode:
        garage('key', 'import', '--yes', '-n', 'homelab-loki', key,
               values['LOKI_S3_SECRET_KEY'])
        changed = True
    # The CLI prints bucket permissions, without requiring the secret key.
    info = garage('bucket', 'info', bucket).stdout
    if key not in info or changed:
        garage('bucket', 'allow', '--read', '--write', '--owner', bucket, '--key', key)
        changed = True
    print('changed=' + str(changed).lower())


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Logging object-store provisioning failed; inspect the private service configuration.', file=sys.stderr)
        sys.exit(1)
