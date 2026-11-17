#!/usr/bin/env python3
"""Check the proxy network address plan and its guarded recreation.

The inventory checks need no Docker. The integration checks run the whole
networks role against UUID-named networks on the local Docker daemon and remove
them afterwards. No managed host is contacted.
"""
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'roles/networks/files/recreate_network.py'
SUBNET, GATEWAY, IPRANGE, STATIC = '172.31.0.0/16', '172.31.0.1', '172.31.128.0/17', '172.31.0.43'
PLAN = {'subnet': SUBNET, 'gateway': GATEWAY, 'iprange': IPRANGE}
IMAGE = 'alpine:3.20'


def inventory_hosts(node):
    for name, values in (node.get('hosts') or {}).items():
        yield name, values or {}
    for child in (node.get('children') or {}).values():
        yield from inventory_hosts(child or {})


class InventoryPlan(unittest.TestCase):
    def test_static_addresses_are_outside_the_dynamic_range(self):
        inventory = yaml.safe_load((ROOT / 'inventory/hosts.yml').read_text())
        planned = [(n, v) for n, v in inventory_hosts(inventory['all']) if 'proxy_network_ipam' in v]
        self.assertTrue(planned, 'expected at least one host with proxy_network_ipam')
        for name, values in planned:
            plan = values['proxy_network_ipam']
            subnet = ipaddress.ip_network(plan['subnet'])
            pool = ipaddress.ip_network(plan['iprange'])
            gateway = ipaddress.ip_address(plan['gateway'])
            with self.subTest(host=name):
                self.assertTrue(pool.subnet_of(subnet))
                self.assertIn(gateway, subnet)
                self.assertNotIn(gateway, pool)
                static = values.get('traefik_proxy_ipv4_address')
                if static:
                    self.assertIn(ipaddress.ip_address(static), subnet)
                    self.assertNotIn(ipaddress.ip_address(static), pool)


def docker(*args, check=True):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check)


def docker_endpoint():
    # The Docker modules ignore CLI contexts, so pass the context's socket.
    if os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'):
        return os.environ['DOCKER_HOST']
    return docker('context', 'inspect', '--format', '{{.Endpoints.docker.Host}}').stdout.strip()


def docker_available():
    return bool(shutil.which('docker') and shutil.which('ansible-playbook')
                and docker('info', check=False).returncode == 0)


@unittest.skipUnless(docker_available(), 'needs local Docker and Ansible')
class GuardedRecreation(unittest.TestCase):
    def setUp(self):
        self.id = uuid.uuid4().hex[:12]
        self.proxy = f'nettest-{self.id}-proxy'
        self.others = {key: f'nettest-{self.id}-{key}' for key in ('backend', 'shared', 'cibuild', 'vpn', 'internal')}
        self.temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.addCleanup(self.cleanup)
        if docker('image', 'inspect', IMAGE, check=False).returncode:
            docker('pull', '-q', IMAGE)
        docker('network', 'create', '--subnet', SUBNET, '--gateway', GATEWAY, self.proxy)
        docker('network', 'create', '--internal', self.others['internal'])
        self.run_container('static', '--ip', STATIC)
        self.run_container('svc', '--network-alias', 'web')
        self.run_container('dual')
        docker('network', 'connect', self.others['internal'], self.c('dual'))
        docker('run', '--name', self.c('exited'), '--network', self.proxy, IMAGE, 'true')
        self.before = {name: self.address(name) for name in ('static', 'svc', 'dual')}

    def c(self, name):
        return f'nettest-{self.id}-{name}'

    def run_container(self, name, *args):
        docker('run', '-d', '--name', self.c(name), '--network', self.proxy, *args, IMAGE, 'sleep', '600')

    def cleanup(self):
        for name in ('static', 'svc', 'dual', 'exited', 'new'):
            docker('rm', '-f', self.c(name), check=False)
        for network in (self.proxy, *self.others.values()):
            docker('network', 'rm', network, check=False)

    def run_role(self, *extra, plan=True, restart=None, expect=0):
        variables = {
            'proxy_network': self.proxy,
            'backend_network': self.others['backend'],
            'shared_network': self.others['shared'],
            'cibuild_network': self.others['cibuild'],
            'vpn_network': self.others['vpn'],
            'networks_snapshot_dir': str(self.temp / 'snapshots'),
            'networks_proxy_restart': restart or [],
            'ansible_python_interpreter': sys.executable,
        }
        if plan:
            variables['proxy_network_ipam'] = PLAN
        playbook = self.temp / 'play.yml'
        playbook.write_text(yaml.safe_dump([{
            'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
            'vars': variables, 'roles': ['networks']}]))
        config = self.temp / 'ansible.cfg'
        config.write_text('[defaults]\n')
        env = dict(os.environ, ANSIBLE_ROLES_PATH=str(ROOT / 'roles'), ANSIBLE_CONFIG=str(config),
                   ANSIBLE_LOCALHOST_WARNING='false', ANSIBLE_INVENTORY_UNPARSED_WARNING='false',
                   DOCKER_HOST=docker_endpoint())
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(playbook), *extra],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result.stdout

    def network(self):
        return json.loads(docker('network', 'inspect', self.proxy).stdout)[0]

    def inspect(self, name):
        return json.loads(docker('inspect', self.c(name)).stdout)[0]

    def address(self, name):
        return self.inspect(name)['NetworkSettings']['Networks'][self.proxy]['IPAddress']

    def assert_untouched(self, network_id):
        self.assertEqual(self.network()['Id'], network_id)
        self.assertEqual(len(self.network()['Containers']), 3)
        self.assertEqual({n: self.address(n) for n in self.before}, self.before)

    def test_without_plan_the_role_is_idempotent(self):
        before = self.network()['Id']
        self.run_role(plan=False)
        self.assertIn('changed=0', self.run_role(plan=False))
        self.assert_untouched(before)

    def test_mismatch_without_flag_leaves_network_attached(self):
        before = self.network()['Id']
        self.assertIn('was left unchanged', self.run_role())
        self.assert_untouched(before)

    def test_check_mode_with_flag_changes_nothing(self):
        before = self.network()['Id']
        self.run_role('--check', '-e', 'networks_recreate_proxy=true')
        self.assert_untouched(before)

    def test_flag_recreates_and_preserves_endpoints(self):
        started = self.inspect('static')['State']['StartedAt']
        self.run_role('-e', 'networks_recreate_proxy=true', restart=[self.c('static')])
        self.assertEqual(self.network()['IPAM']['Config'],
                         [{'Subnet': SUBNET, 'IPRange': IPRANGE, 'Gateway': GATEWAY}])
        # Addresses outside the new dynamic range are kept, so cached peers stay valid.
        self.assertEqual({n: self.address(n) for n in self.before}, self.before)
        self.assertNotEqual(self.inspect('static')['State']['StartedAt'], started)
        docker('exec', self.c('static'), 'ping', '-c1', '-W2', 'web')
        route = docker('exec', self.c('dual'), 'ip', 'route').stdout
        self.assertIn(f'default via {GATEWAY}', route)
        # A stopped container that ran before stores the old network ID.
        docker('start', self.c('exited'))
        docker('run', '-d', '--name', self.c('new'), '--network', self.proxy, IMAGE, 'sleep', '600')
        self.assertIn(ipaddress.ip_address(self.address('new')), ipaddress.ip_network(IPRANGE))
        snapshots = list((self.temp / 'snapshots').glob('*.json'))
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].stat().st_mode & 0o777, 0o600)

        after = self.network()['Id']
        self.assertIn('changed=0', self.run_role('-e', 'networks_recreate_proxy=true'))
        self.assertIn('changed=0', self.run_role())
        self.assertEqual(self.network()['Id'], after)

    def test_failed_create_restores_original_network(self):
        original = self.network()['IPAM']['Config']
        result = subprocess.run([sys.executable, str(SCRIPT), '--name', self.proxy, '--subnet', SUBNET,
                                 '--gateway', GATEWAY, '--ip-range', '10.99.0.0/24',
                                 '--snapshot-dir', str(self.temp / 'snapshots')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('restored original IPAM', result.stderr)
        self.assertIn('snapshot:', result.stderr)
        self.assertEqual(self.network()['IPAM']['Config'], original)
        self.assertEqual(len(self.network()['Containers']), 3)
        self.assertEqual({n: self.address(n) for n in self.before}, self.before)
        docker('start', self.c('exited'))


if __name__ == '__main__':
    unittest.main()
