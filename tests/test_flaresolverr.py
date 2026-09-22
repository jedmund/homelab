#!/usr/bin/env python3
"""Render the actual service/ACL templates with disposable values; no host access."""
from pathlib import Path
import sys
import unittest

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/flaresolverr'


def render(name, **overrides):
    values = yaml.safe_load((ROOT / 'group_vars/compute_servers/common.yml').read_text())
    values.update(yaml.safe_load((ROLE / 'defaults/main.yml').read_text()))
    values.update(ansible_managed='test', stack_name='flaresolverr',
                  flaresolverr_bind_address='192.0.2.6',
                  flaresolverr_allowed_sources=['192.0.2.100/32'])
    values.update(overrides)
    return jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(
        (ROLE / 'templates' / name).read_text()).render(values)


class FlareSolverrTests(unittest.TestCase):
    def test_compose_exposure_and_resources(self):
        document = yaml.safe_load(render('compose.yaml.j2'))
        service = document['services']['flaresolverr']
        self.assertEqual(service['ports'], ['127.0.0.1:8191:8191', '192.0.2.6:8191:8191'])
        self.assertIn('@sha256:', service['image'])
        self.assertEqual(service['mem_limit'], '2g')
        self.assertEqual(service['cpus'], 2)
        self.assertEqual(service['environment']['LOG_HTML'], 'false')
        self.assertEqual(service['environment']['LOG_LEVEL'], 'warning')
        self.assertNotIn('volumes', service)
        self.assertNotIn('privileged', service)
        self.assertNotIn('labels', service)
        self.assertEqual(service['networks'], ['shared'])
        self.assertIn('/health', service['healthcheck']['test'][-1])

    def test_acl_is_service_scoped_and_handles_dnat(self):
        rules = render('firewall.nft.j2')
        self.assertNotIn('flush ruleset', rules)
        self.assertIn('flush table inet homelab_flaresolverr', rules)
        self.assertIn('ct direction original ct original ip daddr 192.0.2.6', rules)
        self.assertIn('ct original proto-dst 8191', rules)
        self.assertIn('192.0.2.100/32', rules)
        self.assertNotIn('0.0.0.0/0', rules)
        self.assertEqual(rules.count('ip saddr != @allowed_v4 drop'), 2)

    def test_changed_allowlist_replaces_old_members(self):
        rules = render('firewall.nft.j2', flaresolverr_allowed_sources=['192.0.2.101/32'])
        self.assertIn('192.0.2.101/32', rules)
        self.assertNotIn('192.0.2.100/32', rules)

    def test_boot_is_fail_closed_without_a_docker_restart(self):
        unit = render('firewall.service.j2')
        dropin = render('docker-firewall.conf.j2')
        self.assertIn('Before=docker.service', unit)
        self.assertNotIn('ExecStop=', unit)
        self.assertIn('Requires=flaresolverr-firewall.service', dropin)
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        firewall = next(i for i, t in enumerate(tasks) if t['name'].startswith('Load FlareSolverr firewall'))
        compose = next(i for i, t in enumerate(tasks) if 'community.docker.docker_compose_v2' in t)
        self.assertLess(firewall, compose)
        self.assertEqual(sum('community.docker.docker_compose_v2' in t for t in tasks), 1)


if __name__ == '__main__':
    if '--print-firewall' in sys.argv:
        print(render('firewall.nft.j2'))
    else:
        unittest.main()

