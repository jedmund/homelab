#!/usr/bin/env python3
"""Transfer failures must retain the previously published snapshot."""
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import unittest

import jinja2

ROOT = Path(__file__).resolve().parents[1]


class Transfer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.tar'
        self.output = self.root / 'destination'
        self.output.mkdir()
        self.previous = self.output / 'snapshot.tar'
        self.previous.write_bytes(b'previous-complete')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        scripts = {'flock': 'exit 0', 'timeout': 'shift; exec "$@"',
                   'ssh': 'cat "$SOURCE_TAR"; exit "${SSH_RESULT:-0}"'}
        for name, content in scripts.items():
            p = self.bin / name
            p.write_text('#!/bin/sh\n' + content + '\n')
            p.chmod(0o755)
        self.env = os.environ | {'PATH': str(self.bin) + ':' + os.environ['PATH'],
                                 'SOURCE_TAR': str(self.source)}
        template = (ROOT / 'roles/backup/templates/scripts/pull-minecraft.sh.j2').read_text()
        rendered = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(template).render(
            ansible_managed='fixture', hostvars={'max': {'ansible_host': 'fixture', 'ansible_port': 22}},
            backup_verification_max_age_hours=27)
        self.script = self.root / 'pull.sh'
        self.script.write_text(rendered.replace('root=/minecraft', 'root=' + str(self.output)))

    def archive(self, age=0):
        with tarfile.open(self.source, 'w') as archive:
            value = str(int(time.time()) - age).encode()
            info = tarfile.TarInfo('./snapshot-time')
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))

    def execute(self):
        return subprocess.run(['bash', str(self.script)], env=self.env, capture_output=True)

    def test_complete_transfer_publishes(self):
        self.archive()
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.previous.read_bytes(), self.source.read_bytes())

    def test_failed_ssh_preserves_previous(self):
        self.archive()
        self.env['SSH_RESULT'] = '1'
        self.assertNotEqual(self.execute().returncode, 0)
        self.assertEqual(self.previous.read_bytes(), b'previous-complete')
        self.assertFalse(list(self.output.glob('.snapshot.*')))

    def test_stale_snapshot_preserves_previous(self):
        self.archive(age=28 * 3600)
        self.assertNotEqual(self.execute().returncode, 0)
        self.assertEqual(self.previous.read_bytes(), b'previous-complete')

    def test_corrupt_stream_preserves_previous(self):
        self.source.write_bytes(b'truncated stream')
        self.assertNotEqual(self.execute().returncode, 0)
        self.assertEqual(self.previous.read_bytes(), b'previous-complete')

    def test_missing_nas_refuses_mirror(self):
        template = (ROOT / 'roles/backup/templates/scripts/post-backup-rsync.sh.j2').read_text()
        rendered = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(template).render(
            ansible_managed='fixture', borg_repo_container_path=str(self.root / 'repo'),
            nas_mount_container_path=str(self.root / 'nas'), nas_share_subpath='mirror',
            backup_nas_rsync_kib_per_second=20000)
        mounts = self.root / 'mounts'
        mounts.write_text('root / ext4 rw 0 0\n')
        script = self.root / 'mirror.sh'
        script.write_text(rendered.replace('/proc/mounts', str(mounts)))
        result = subprocess.run(['bash', str(script)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'not an NFS mount', result.stderr)
        self.assertFalse((self.root / 'nas').exists())


if __name__ == '__main__':
    unittest.main()
