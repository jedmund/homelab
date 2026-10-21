#!/usr/bin/env python3
"""Check recreation inputs against the role's reachable task order."""

from pathlib import Path
import tempfile
import unittest

import yaml

from compose_lifecycle import COMPOSE, check_recreation_order


class RecreationOrderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.deploy = {
            'name': 'Deploy fixture',
            COMPOSE: {
                'recreate': "{{ 'always' if fixture_config.changed | default(false) else 'auto' }}",
            },
        }
        self.configure = {
            'name': 'Configure fixture',
            'ansible.builtin.debug': {'msg': 'fixture'},
            'register': 'fixture_config',
        }

    def write_tasks(self, name, items):
        path = self.root / name
        path.write_text(yaml.safe_dump(items))
        return path

    def test_nested_includes_and_imports_precede_deployment(self):
        # Create main first: directory enumeration must not decide task order.
        main = self.write_tasks('main.yml', [
            {'ansible.builtin.include_tasks': 'included.yml'}, self.deploy,
        ])
        self.write_tasks('included.yml', [{
            'block': [{'ansible.builtin.import_tasks': {'file': 'config.yml'}}],
        }])
        self.write_tasks('config.yml', [self.configure])
        check_recreation_order(main)

    def test_include_after_deployment_does_not_supply_prior_result(self):
        self.write_tasks('config.yml', [self.configure])
        main = self.write_tasks('main.yml', [
            self.deploy, {'ansible.builtin.include_tasks': 'config.yml'},
        ])
        with self.assertRaisesRegex(AssertionError, 'fixture_config'):
            check_recreation_order(main)

    def test_unreferenced_file_does_not_supply_prior_result(self):
        self.write_tasks('unused.yml', [self.configure])
        main = self.write_tasks('main.yml', [self.deploy])
        with self.assertRaisesRegex(AssertionError, 'fixture_config'):
            check_recreation_order(main)


if __name__ == '__main__':
    unittest.main()
