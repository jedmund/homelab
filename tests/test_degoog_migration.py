#!/usr/bin/env python3
"""Exercise the production migration helper using disposable files and SQLite."""
import importlib.util
import io
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('migration', ROOT / 'roles/degoog/files/migration.py')
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='degoog-migration-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.destination = self.root / 'destination'
        (self.source / 'data').mkdir(parents=True)
        self.destination.mkdir()
        (self.source / 'data/settings.json').write_text('{"fixture":true}')
        with sqlite3.connect(self.source / 'data/index.db') as db:
            db.execute('CREATE TABLE fixture (value TEXT)')
            db.execute("INSERT INTO fixture VALUES ('preserved')")
        self.archive = self.root / 'data.tar.gz'
        migration.archive(self.source, self.archive)
        self.checksum = migration.digest(self.archive)

    def test_stopped_transfer_and_idempotency(self):
        self.assertTrue(migration.restore(self.destination, self.archive, self.checksum))
        self.assertEqual(migration.checkpoint(self.destination)['state'], 'restored')
        with sqlite3.connect(self.destination / 'data/index.db') as db:
            self.assertEqual(db.execute('SELECT value FROM fixture').fetchone(), ('preserved',))
        live = self.destination / 'data/settings.json'
        live.write_text('{"updated":true}')
        self.assertFalse(migration.restore(self.destination, self.archive, self.checksum))
        self.assertEqual(live.read_text(), '{"updated":true}')

    def test_destination_collision_refuses_before_mutation(self):
        data = self.destination / 'data'
        data.mkdir()
        (data / 'existing').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            migration.restore(self.destination, self.archive, self.checksum)
        self.assertEqual((data / 'existing').read_text(), 'keep')

    def test_checksum_failure_does_not_restore(self):
        with self.assertRaisesRegex(ValueError, 'checksum'):
            migration.restore(self.destination, self.archive, '0' * 64)
        self.assertFalse((self.destination / 'data').exists())

    def test_corrupt_sqlite_refuses_archive(self):
        (self.source / 'data/broken.db').write_bytes(b'SQLite format 3\x00' + b'broken' * 100)
        with self.assertRaises(sqlite3.DatabaseError):
            migration.archive(self.source, self.root / 'broken.tar.gz')
        self.assertFalse((self.root / 'broken.tar.gz').exists())

    def test_resume_after_directory_move_before_marker(self):
        original = migration.write_checkpoint

        def interrupt(root, state, checksum):
            if state == 'restored':
                raise RuntimeError('simulated interruption')
            original(root, state, checksum)

        with patch.object(migration, 'write_checkpoint', side_effect=interrupt):
            with self.assertRaises(RuntimeError):
                migration.restore(self.destination, self.archive, self.checksum)
        self.assertEqual(migration.checkpoint(self.destination)['state'], 'prepared')
        self.assertTrue(migration.restore(self.destination, self.archive, self.checksum))
        self.assertEqual(migration.checkpoint(self.destination)['state'], 'restored')

    def test_prepared_destination_drift_is_not_overwritten(self):
        migration.restore(self.destination, self.archive, self.checksum)
        migration.write_checkpoint(self.destination, 'prepared', self.checksum)
        (self.destination / 'data/settings.json').write_text('keep changed data')
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            migration.restore(self.destination, self.archive, self.checksum)
        self.assertEqual((self.destination / 'data/settings.json').read_text(), 'keep changed data')

    def test_unsafe_archive_refused(self):
        with tarfile.open(self.archive, 'w:gz') as bundle:
            member = tarfile.TarInfo('data/../../escape')
            member.size = 1
            bundle.addfile(member, io.BytesIO(b'x'))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            migration.restore(self.destination, self.archive, migration.digest(self.archive))
        self.assertFalse((self.root / 'escape').exists())

    def test_symlinks_and_unknown_checkpoints_refused(self):
        (self.source / 'data/link').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            migration.validate_data(self.source / 'data')
        (self.destination / '.degoog-migration.json').write_text('{"migration":"someone-else"}')
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            migration.preflight(self.destination)

    def test_resume_prepared_before_directory_move(self):
        migration.write_checkpoint(self.destination, 'prepared', self.checksum)
        self.assertTrue(migration.restore(self.destination, self.archive, self.checksum))

    def test_local_deployment_keeps_auth_and_has_no_lan_binding(self):
        values = yaml.safe_load((ROOT / 'group_vars/compute_servers/common.yml').read_text())
        values.update(yaml.safe_load((ROOT / 'roles/degoog/defaults/main.yml').read_text()))
        values.update(ansible_managed='test', degoog_base_url='https://search.example.test',
                      degoog_puid='977', degoog_pgid='988')
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        env.filters['urlsplit'] = lambda value, field: getattr(urlsplit(value), field)
        result = yaml.safe_load(env.from_string(
            (ROOT / 'roles/degoog/templates/compose.yaml.j2').read_text()).render(values))
        app = result['services']['degoog']
        self.assertEqual(app['ports'], ['127.0.0.1:4444:4444'])
        self.assertEqual(app['labels']['traefik.http.routers.degoog.middlewares'], 'tinyauth@file')
        self.assertEqual(app['labels']['traefik.http.routers.degoog.rule'], 'Host(`search.example.test`)')
        self.assertEqual(app['volumes'], ['./data:/app/data'])
        self.assertIn('@sha256:', app['image'])

    def test_cutover_is_explicit_and_preserves_extensions(self):
        play = yaml.safe_load((ROOT / 'deploy/degoog_migrate.yml').read_text())[0]
        self.assertIn('degoog_migration_confirm', str(play['tasks'][0]))
        tasks = yaml.safe_load((ROOT / 'roles/degoog/tasks/migrate.yml').read_text())
        cutover = next(t['block'] for t in tasks if t['name'] == 'Apply the destination and switch the route')
        app = next(t for t in cutover if t.get('ansible.builtin.include_role', {}).get('name') == 'degoog')
        self.assertFalse(app['vars']['degoog_manage_extensions'])
        public = next(t['ansible.builtin.uri'] for t in cutover
                      if t.get('ansible.builtin.uri', {}).get('url') == '{{ degoog_base_url }}')
        self.assertEqual(public['headers']['Accept'], 'text/html')
        self.assertEqual(public['follow_redirects'], 'none')
        self.assertEqual(public['status_code'], [302, 303, 307])


if __name__ == '__main__':
    unittest.main()
