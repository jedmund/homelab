#!/usr/bin/env python3
"""Verify RomM's co-owned configuration survives the 5.4 migration."""
import copy
from pathlib import Path
import unittest

from ansible.plugins.filter.core import FilterModule
from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[1]


class RommConfigTests(unittest.TestCase):
    def setUp(self):
        self.defaults = yaml.safe_load((ROOT / 'roles/romm/defaults/main.yml').read_text())
        environment = Environment(undefined=StrictUndefined)
        environment.filters.update(FilterModule().filters())
        self.template = environment.from_string(
            (ROOT / 'roles/romm/templates/config.yml.j2').read_text()
        )

    def render(self, existing):
        return yaml.safe_load(self.template.render(
            **self.defaults, romm_existing_config=existing
        ))

    def test_legacy_migration_preserves_ui_settings(self):
        existing = {
            'filesystem': {'roms_folder': 'roms', 'firmware_folder': 'bios',
                           'skip_hash_calculation': True},
            'system': {'platforms': {'GCN': 'ngc', 'PS2': 'ps2'}},
            'exclude': {'platforms': ['win']},
            'emulatorjs': {'debug': True},
            'streaming': {'enabled': False, 'containers': []},
        }
        result = self.render(existing)
        for key in ('system', 'exclude', 'emulatorjs'):
            self.assertEqual(result[key], existing[key])
        self.assertEqual(result['filesystem'], {
            'skip_hash_calculation': True,
            'structure': self.defaults['romm_filesystem_structure'],
        })
        self.assertEqual(result['streaming']['containers'],
                         self.defaults['romm_streaming_containers'])

    def test_explicit_structure_survives_repeated_deployment(self):
        existing = {'filesystem': {'structure': {
            'default': 'custom/{platform}/{game}', 'firmware': 'firmware/{platform}',
            'PS2': 'custom/{platform}/{region}/{game}',
        }}}
        original = copy.deepcopy(existing)
        result = self.render(existing)
        self.assertEqual(result['filesystem'], original['filesystem'])
        self.assertEqual(self.render(result), result)
        self.assertEqual(existing, original)

    def test_config_change_only_changes_application_definition(self):
        environment = Environment(undefined=StrictUndefined)
        environment.filters.update(FilterModule().filters())
        values = dict(self.defaults, romm_existing_config={}, ansible_managed='fixture',
                      restart_policy='unless-stopped', shared_network='shared',
                      backend_network='backend', healthcheck_interval='30s',
                      healthcheck_timeout='10s', healthcheck_retries=3,
                      logging_driver='json-file', logging_max_size='10m',
                      logging_max_file='3', romm_db_password='placeholder',
                      romm_db_root_password='placeholder', romm_auth_secret_key='placeholder',
                      romm_oidc_client_id='placeholder', romm_oidc_client_secret='placeholder')

        def lookup(plugin, filename):
            return environment.from_string(
                (ROOT / 'roles/romm/templates' / filename).read_text()
            ).render(**values)

        environment.globals['lookup'] = lookup
        compose = environment.from_string(
            (ROOT / 'roles/romm/templates/compose.yaml.j2').read_text()
        )
        before = yaml.safe_load(compose.render(**values))
        values['romm_existing_config'] = {'exclude': {'platforms': ['win']}}
        after = yaml.safe_load(compose.render(**values))
        self.assertEqual(before['services']['romm-db'], after['services']['romm-db'])
        self.assertNotEqual(before['services']['romm']['labels'],
                            after['services']['romm']['labels'])
        self.assertEqual(after, yaml.safe_load(compose.render(**values)))
        values['romm_oidc_client_secret'] = 'changed-placeholder'
        changed_env = yaml.safe_load(compose.render(**values))
        self.assertNotEqual(after['services']['romm']['labels'],
                            changed_env['services']['romm']['labels'])
        self.assertEqual(after['services']['romm-db'], changed_env['services']['romm-db'])

    def test_empty_configuration_gets_explicit_layout(self):
        self.assertEqual(self.render({})['filesystem']['structure'],
                         self.defaults['romm_filesystem_structure'])


if __name__ == '__main__':
    unittest.main()
