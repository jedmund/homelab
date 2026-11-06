#!/usr/bin/env python3
"""Test production Borg wrapper locking in an existing Linux container.

DOCKER_HOST=ssh://nuc python3 tests/test_minecraft_lock.py borgmatic
Only a disposable /tmp directory is used; no archive operation is invoked.
"""
import base64
from pathlib import Path
import subprocess
import sys

source = (Path(__file__).resolve().parents[1] /
          'roles/backup/templates/scripts/borg-locked.sh.j2').read_text()
source = source.replace('{{ ansible_managed }}', 'test').replace('/minecraft/transfer.lock', '"$TEST_LOCK"')
encoded = base64.b64encode(source.encode()).decode()
script = r'''
set -euo pipefail
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export TEST_LOCK="$tmp/lock" TEST_MARKER="$tmp/reader" TEST_WRITER="$tmp/writer"
export PATH="$tmp:$PATH"
base64 -d > "$tmp/wrapper" <<'BASE64'
ENCODED
BASE64
cat > "$tmp/borg" <<'BORG'
#!/bin/sh
touch "$TEST_MARKER"
sleep 2
BORG
chmod +x "$tmp/borg"
flock -x "$TEST_LOCK" sh -c 'touch "$TEST_WRITER"; sleep 2' &
writer=$!
for i in $(seq 1 50); do test -f "$TEST_WRITER" && break; sleep .1; done
test -f "$TEST_WRITER"
bash "$tmp/wrapper" --version &
reader=$!
sleep .2
test ! -f "$TEST_MARKER"
wait "$writer"
for i in $(seq 1 50); do test -f "$TEST_MARKER" && break; sleep .1; done
test -f "$TEST_MARKER"
if flock -n "$TEST_LOCK" true; then
    echo 'Publication was allowed during a Borg reader' >&2
    exit 1
fi
wait "$reader"
flock -n "$TEST_LOCK" true
echo 'PASS publication and Borg readers exclude each other and release locks'
'''.replace('ENCODED', encoded)
subprocess.run(['docker', 'exec', '-i', sys.argv[1], 'bash', '-s'], input=script, text=True, check=True)
