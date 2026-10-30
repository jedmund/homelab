#!/usr/bin/env python3
"""Render AI access controls with disposable values; no managed-host access."""
import json
from pathlib import Path
import shlex
import sys
import unittest

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/ai'


def render(name, **overrides):
    values = yaml.safe_load((ROOT / 'group_vars/compute_servers/common.yml').read_text())
    values.update(yaml.safe_load((ROLE / 'defaults/main.yml').read_text()))
    values.update(ansible_managed='test', stack_name='ai', ai_gpu_mode='split',
                  ai_llama_swap_bind_address='192.0.2.100',
                  ai_llama_swap_allowed_sources=['192.0.2.0/24'])
    values.update(overrides)
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.filters['to_json'] = json.dumps
    env.filters['bool'] = lambda value: str(value).lower() in ('true', '1', 'yes', 'on')
    return env.from_string((ROLE / 'templates' / name).read_text()).render(values)


class AIAccessTests(unittest.TestCase):
    def test_published_port_is_ipv4_only_in_both_gpu_modes(self):
        for mode in ('split', 'shared'):
            with self.subTest(mode=mode):
                document = yaml.safe_load(render('compose.yaml.j2', ai_gpu_mode=mode))
                service = document['services']['llama-swap']
                self.assertEqual(service['ports'],
                                 ['127.0.0.1:11434:8080', '192.0.2.100:11434:8080'])
                self.assertIn('http://localhost:8080/health', service['healthcheck']['test'])

    def test_children_use_container_loopback_and_restricted_cors(self):
        for mode in ('split', 'shared'):
            with self.subTest(mode=mode):
                document = yaml.safe_load(render('config/llama-swap.yaml.j2', ai_gpu_mode=mode))
                self.assertTrue(document['models'])
                for model in document['models'].values():
                    command = shlex.split(model['cmd'])
                    self.assertEqual(command[command.index('--host') + 1], '127.0.0.1')
                    self.assertEqual(command[command.index('--cors-origins') + 1], 'localhost')

    def test_openjev_has_vision_without_sharing_the_chat_swap_slot(self):
        for mode in ('split', 'shared'):
            with self.subTest(mode=mode):
                document = yaml.safe_load(render('config/llama-swap.yaml.j2', ai_gpu_mode=mode))
                model = document['models']['openjev']
                command = shlex.split(model['cmd'])
                self.assertEqual(command[command.index('--model') + 1],
                                 '/models/OpenJev/OpenJev-Q8_0.gguf')
                self.assertEqual(command[command.index('--mmproj') + 1],
                                 '/models/OpenJev/mmproj-OpenJev-BF16.gguf')
                self.assertIn('--jinja', command)
                self.assertEqual(command[command.index('-c') + 1], '16384')
                self.assertEqual(command[command.index('--parallel') + 1], '1')
                self.assertEqual(model['ttl'], 300)
                group = document['groups']['decision']
                self.assertIn('openjev', group['members'])
                self.assertTrue(group['swap'])
                self.assertFalse(group['exclusive'])
                self.assertFalse(group.get('persistent', False))
                self.assertNotIn('openjev', document['groups']['chat']['members'])

    def test_firewall_matches_published_destination_after_dnat(self):
        rules = render('firewall.nft.j2')
        self.assertNotIn('flush ruleset', rules)
        self.assertIn('delete table inet homelab_llama_swap', rules)
        self.assertNotIn('flush table', rules)
        self.assertIn('hook forward priority -10', rules)
        self.assertIn('ct direction original ct original ip daddr 192.0.2.100', rules)
        self.assertIn('ct original proto-dst 11434', rules)
        self.assertIn('192.0.2.0/24', rules)
        self.assertNotIn('established', rules)
        self.assertEqual(rules.count('ip saddr != @allowed_v4 drop'), 2)

    def test_empty_and_replaced_allowlists_remove_previous_sources(self):
        for sources in ([], ['192.0.2.7/32', '192.0.2.8/32']):
            with self.subTest(sources=sources):
                rules = render('firewall.nft.j2', ai_llama_swap_allowed_sources=sources)
                self.assertNotIn('192.0.2.0/24', rules)
                self.assertIn('127.0.0.1/32', rules)
                for source in sources:
                    self.assertIn(source, rules)

    def test_firewall_precedes_publication_and_docker_boot(self):
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        self.assertEqual(tasks[0]['ansible.builtin.import_tasks'], 'firewall.yml')
        self.assertEqual(sum('community.docker.docker_compose_v2' in t for t in tasks), 1)
        unit = render('firewall.service.j2')
        dropin = render('docker-firewall.conf.j2')
        self.assertIn('Before=docker.service', unit)
        self.assertNotIn('ExecStop=', unit)
        self.assertIn('Requires=ai-llama-swap-firewall.service', dropin)
        firewall_tasks = yaml.safe_load((ROLE / 'tasks/firewall.yml').read_text())
        apply = next(t['ansible.builtin.systemd_service'] for t in firewall_tasks
                     if 'ansible.builtin.systemd_service' in t)
        self.assertIn("'reloaded'", apply['state'])
        self.assertNotIn("'restarted'", apply['state'])


if __name__ == '__main__':
    if '--print-firewall' in sys.argv:
        print(render('firewall.nft.j2'))
    else:
        unittest.main()
