"""Render production Compose and evaluate admission assertions without contacting hosts."""
from pathlib import Path
import unittest
import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/album_sort'


class TagConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        self.values = {}
        for path in ['group_vars/compute_servers/common.yml', 'group_vars/compute_servers/docker.yml', 'roles/album_sort/defaults/main.yml']:
            self.values.update(yaml.safe_load((ROOT / path).read_text()))
        self.values.update(ansible_managed='test fixture', music_volume_name='music', ansible_user='fixture')
        self.assertions = next(task['ansible.builtin.assert']['that'] for task in yaml.safe_load((ROLE / 'tasks/main.yml').read_text()) if task.get('name') == 'Validate Album Sort tag preparation limits')

    def valid(self, settings):
        values = self.values | settings
        return all(self.env.compile_expression(expression)(values) for expression in self.assertions)

    def test_renders_baseline_and_candidate_without_changing_volume(self):
        source = (ROLE / 'templates/compose.yaml.j2').read_text()
        for preflight, staging, copy in [('1', '1', '1'), ('2', '2', '1')]:
            values = self.values | {'album_sort_tag_preflight_concurrency': preflight, 'album_sort_tag_staging_concurrency': staging, 'album_sort_tag_copy_concurrency': copy}
            rendered = yaml.safe_load(self.env.from_string(source).render(values))
            service = rendered['services']['album-sort']
            self.assertEqual(service['environment']['TAG_PREFLIGHT_CONCURRENCY'], preflight)
            self.assertEqual(service['environment']['TAG_STAGING_CONCURRENCY'], staging)
            self.assertEqual(service['environment']['TAG_COPY_CONCURRENCY'], copy)
            self.assertIn('music:/music', service['volumes'])
            self.assertTrue(self.valid(values))

    def test_rejects_bad_limits_before_deployment(self):
        for name in ['preflight', 'staging', 'copy']:
            for value in ['', '0', '3', '8', '2.0', ' 2']:
                self.assertFalse(self.valid({f'album_sort_tag_{name}_concurrency': value}))
        self.assertFalse(self.valid({'album_sort_tag_copy_concurrency': '2'}))


if __name__ == '__main__':
    unittest.main()
