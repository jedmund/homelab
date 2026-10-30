#!/usr/bin/env python3
"""Create consistent local metadata snapshots for the encrypted Borg backup."""
from pathlib import Path
import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.request


def snapshot_prometheus(root, port):
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}/api/v1/admin/tsdb/snapshot', method='POST')
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    name = result['data']['name']
    if result['status'] != 'success' or not re.fullmatch(r'[0-9TZ]+-[0-9a-f]+', name):
        raise RuntimeError('Prometheus snapshot failed')
    source = root / 'prometheus-data/snapshots' / name
    target = root / 'backup/prometheus'
    temporary = root / 'backup/prometheus.next'
    previous = root / 'backup/prometheus.previous'
    for stale in [temporary, previous]:
        if stale.exists():
            shutil.rmtree(stale)
    # TSDB snapshots contain immutable blocks. Hard links avoid copying the
    # full database while keeping the Borg restore artifact outside live data.
    shutil.copytree(source, temporary, copy_function=os.link)
    temporary.chmod(0o700)
    if target.exists():
        os.replace(target, previous)
    os.replace(temporary, target)
    if previous.exists():
        shutil.rmtree(previous)
    shutil.rmtree(source)


def snapshot(root, port):
    target = root / 'backup/grafana.db'
    source = root / 'grafana-data/grafana.db'
    os.umask(0o077)
    with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as original:
        with sqlite3.connect(str(target) + '.tmp') as backup:
            original.backup(backup)
            assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    os.replace(str(target) + '.tmp', target)
    result = subprocess.run(['docker', 'exec', 'logging-garage', '/garage', 'meta', 'snapshot'],
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError('Garage metadata snapshot failed')
    snapshot_prometheus(root, port)
    (root / 'backup/snapshot.ok').touch()


def main():
    root = Path(sys.argv[1])
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 19090
    os.umask(0o077)
    with (root / 'backup/.snapshot.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        snapshot(root, port)


if __name__ == '__main__':
    main()
