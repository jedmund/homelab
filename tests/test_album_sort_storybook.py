"""Exercise the Komodo action without contacting managed hosts."""
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = tomllib.loads((ROOT / 'komodo/stacks.toml').read_text())
ACTION = next(a for a in DATA['action'] if a['name'] == 'album-sort-storybook')


class StorybookActionTests(unittest.TestCase):
    def run_action(self, args, existing=False, succeeds=True):
        prefix = f'''
const ARGS = {json.dumps(args)};
const calls = [];
const YAML = {{ stringify: JSON.stringify }};
const komodo = {{
  read: async () => {json.dumps([{'id': 'owned', 'name': 'album-sort-storybook-mr-12'}] if existing else [])},
  write: async (operation, params) => {{ calls.push({{operation, params}}); return {{name: params.name ?? 'owned'}}; }},
  execute_and_poll: async (operation, params) => {{ calls.push({{operation, params}}); return {{success: {str(succeeds).lower()}}}; }}
}};
'''
        script = prefix + '\ntry {\n' + ACTION['config']['file_contents'] + '''
 console.log(JSON.stringify({ok: true, calls}));
} catch (error) { console.log(JSON.stringify({ok: false, calls, error: error.message})); }
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'action.ts'
            path.write_text(script)
            output = subprocess.check_output(['node', '--experimental-strip-types', str(path)], text=True)
        return json.loads(output.strip().splitlines()[-1])

    def test_deploy_derives_private_boundaries(self):
        for target in ['main', '12']:
            result = self.run_action({'operation': 'deploy', 'target': target, 'revision': 'a' * 40})
            self.assertTrue(result['ok'], result)
            config = result['calls'][0]['params']['config']
            compose = json.loads(config['file_contents'])
            service = compose['services']['storybook']
            self.assertEqual(service['image'], 'registry.atelier.house/jedmund/album-sort/storybook:' + 'a' * 40)
            self.assertEqual(service['networks'], ['proxy-network'])
            self.assertNotIn('ports', service)
            self.assertIn('tinyauth@file', service['labels'].values())
            self.assertEqual(config['registry_account'], '')
            self.assertEqual(config['registry_provider'], '')
            self.assertEqual(config['compose_cmd_wrapper'], 'env DOCKER_CONFIG=/etc/komodo/album-sort-storybook [[COMPOSE_COMMAND]]')
            self.assertIn('pull', config['compose_cmd_wrapper_include'])
            self.assertIn('up', config['compose_cmd_wrapper_include'])
            expected = 'album-sort-storybook' if target == 'main' else 'album-sort-storybook-mr-12'
            self.assertEqual(config['links'], [f'https://{expected}.review.atelier.house'])

    def test_rejects_invalid_inputs_before_mutation(self):
        valid = {'operation': 'deploy', 'target': '12', 'revision': 'a' * 40}
        for key, value in [('operation', 'shell'), ('target', '../12'), ('target', '0'), ('target', '-1'), ('revision', 'abc'), ('revision', 'A' * 40)]:
            result = self.run_action({**valid, key: value})
            self.assertFalse(result['ok'])
            self.assertEqual(result['calls'], [])
        self.assertFalse(self.run_action({**valid, 'operation': 'destroy', 'target': 'main'})['ok'])

    def test_stop_is_idempotent_and_failure_preserves_resource(self):
        args = {'operation': 'destroy', 'target': '12'}
        self.assertEqual(self.run_action(args)['calls'], [])
        result = self.run_action(args, existing=True)
        self.assertEqual([c['operation'] for c in result['calls']], ['DestroyStack', 'DeleteStack'])
        result = self.run_action(args, existing=True, succeeds=False)
        self.assertFalse(result['ok'])
        self.assertEqual([c['operation'] for c in result['calls']], ['DestroyStack'])


if __name__ == '__main__':
    unittest.main()
