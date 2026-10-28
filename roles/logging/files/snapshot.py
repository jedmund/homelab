#!/usr/bin/env python3
"""Create consistent local metadata snapshots for the encrypted Borg backup."""
from pathlib import Path
import fcntl
import os
import sqlite3
import subprocess
import sys




def snapshot(root):
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
    (root / 'backup/snapshot.ok').touch()


def main():
    root = Path(sys.argv[1])
    os.umask(0o077)
    with (root / 'backup/.snapshot.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        snapshot(root)


if __name__ == '__main__':
    main()
