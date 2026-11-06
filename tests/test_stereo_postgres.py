"""Render Stereo's Compose file and check the Postgres service and its backup."""
from pathlib import Path
import unittest
import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/stereo'


class StereoPostgresTests(unittest.TestCase):
    def setUp(self):
        values = {}
        for path in ['group_vars/compute_servers/common.yml', 'group_vars/compute_servers/docker.yml', 'roles/stereo/defaults/main.yml']:
            values.update(yaml.safe_load((ROOT / path).read_text()))
        values.update(ansible_managed='test fixture', music_volume_name='music', ansible_user='fixture')
        self.env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        self.values = values
        self.rendered = yaml.safe_load(self.env.from_string((ROLE / 'templates/compose.yaml.j2').read_text()).render(values))
        self.postgres = self.rendered['services']['postgres']
        self.app = self.rendered['services']['stereo']

    def test_postgres_is_c_locale_utf8_and_unpublished(self):
        self.assertEqual(self.postgres['container_name'], 'stereo_postgres')
        self.assertTrue(self.postgres['image'].startswith('postgres:17'))
        self.assertNotIn('ports', self.postgres)
        self.assertEqual(self.postgres['environment']['POSTGRES_INITDB_ARGS'], '--locale=C --encoding=UTF8')
        self.assertIn('./postgres:/var/lib/postgresql/data', self.postgres['volumes'])
        self.assertIn('pg_isready', self.postgres['healthcheck']['test'])
        self.assertEqual(self.rendered['networks']['backup'], {'name': 'backend-internal', 'external': True})
        self.assertNotIn('backup', self.app['networks'])

    def test_app_waits_for_postgres_and_drains_on_stop(self):
        self.assertEqual(self.app['depends_on']['postgres'], {'condition': 'service_healthy'})
        self.assertEqual(self.app['stop_grace_period'], '60s')

    def test_database_url_encodes_the_password(self):
        source = (ROLE / 'templates/env/stereo.env.j2').read_text()
        values = self.values | {
            'stereo_postgres_password': 'p@ss/w:rd%',
            'stereo_apple_music_team_id': '', 'stereo_apple_music_key_id': '',
            'stereo_apple_music_private_key': '', 'stereo_discogs_token': '',
            'stereo_oidc_client_id': '', 'stereo_oidc_client_secret': '',
            'stereo_user_secret_encryption_key': '',
        }
        line = next(l for l in self.env.from_string(source).render(values).splitlines() if l.startswith('DATABASE_URL='))
        self.assertEqual(line, 'DATABASE_URL=postgres://stereo:p%40ss%2Fw%3Ard%25@stereo_postgres:5432/stereo')

    def test_deploy_requires_a_password(self):
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        that = next(task['ansible.builtin.assert']['that'] for task in tasks if task.get('name') == 'Validate the Stereo Postgres password')
        check = lambda password: all(self.env.compile_expression(e)(self.values | {'stereo_postgres_password': password}) for e in that)
        self.assertFalse(check(''))
        self.assertTrue(check('secret'))

    def test_backup_dumps_the_database_and_skips_its_files(self):
        backup = yaml.safe_load((ROOT / 'roles/backup/defaults/main.yml').read_text())
        self.assertIn('/opt/docker/stereo/postgres', backup['borg_exclude_patterns'])
        self.assertIn('backend-internal', backup['borg_networks'])
        self.assertEqual(backup['stereo_db_name'], self.values['stereo_postgres_db'])
        self.assertEqual(backup['stereo_db_user'], self.values['stereo_postgres_user'])
        borgmatic = (ROOT / 'roles/backup/templates/borgmatic.yaml.j2').read_text()
        self.assertIn('hostname: stereo_postgres', borgmatic)


if __name__ == '__main__':
    unittest.main()
