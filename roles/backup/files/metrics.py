#!/usr/bin/env python3
"""Publish cached backup verification results without exposing archive contents."""
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import time


def collect(root, previous, now):
    state = dict(previous)
    try:
        result = subprocess.run([str(root / 'scripts/verify-backup-status.sh')],
                                capture_output=True, text=True, timeout=180, check=False)
        busy = 'Failed to create/acquire the lock' in result.stderr
        ok = result.returncode == 0
        if ok:
            state['verified_timestamp_seconds'] = now
        for label, age in re.findall(r'^(\w+)_age_seconds=(\d+)$', result.stdout, re.MULTILINE):
            state[label + '_timestamp_seconds'] = now - int(age)
    except (OSError, subprocess.TimeoutExpired):
        ok, busy = False, False
    state['verification_ok'] = int(ok)
    state['repository_busy'] = int(busy)
    state['collection_timestamp_seconds'] = now
    marker = root / 'restore-tests/prowlarr-last-success'
    try:
        state['restore_timestamp_seconds'] = int(marker.read_text().strip())
    except (OSError, ValueError):
        pass
    return state


def main():
    root = Path(sys.argv[1])
    directory = root / 'metrics'
    directory.mkdir(exist_ok=True)
    with (directory / '.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        file = directory / 'state.json'
        try:
            previous = json.loads(file.read_text())
        except (OSError, ValueError):
            previous = {}
        state = collect(root, previous, int(time.time()))
        temporary = directory / 'backup.prom.tmp'
        temporary.write_text(''.join(f'homelab_backup_{key} {value}\n'
                                     for key, value in sorted(state.items())))
        temporary.chmod(0o644)
        temporary.replace(directory / 'backup.prom')
        state_temporary = directory / 'state.json.tmp'
        state_temporary.write_text(json.dumps(state) + '\n')
        state_temporary.replace(file)


if __name__ == '__main__':
    main()
