#!/usr/bin/env python3
"""Render the logging deployment with disposable credentials and validate it."""
import configparser
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(role, name, **overrides):
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.filters['to_json'] = json.dumps
    values = {}
    for file in ['common.yml', 'docker.yml', 'storage.yml']:
        values.update(yaml.safe_load((ROOT / 'group_vars/compute_servers' / file).read_text()))
    values.update(yaml.safe_load((ROOT / 'roles' / role / 'defaults/main.yml').read_text()))
    values.update(ansible_managed='test', inventory_hostname='nuc-mini', ansible_host='192.0.2.6',
                  ansible_user_dir='/home/test', ansible_facts={'os_family': 'Debian'},
                  hostvars={'nuc-mini': {'ansible_host': '192.0.2.6', 'traefik_proxy_ipv4_address': '172.18.0.43'},
                            'max': {'ansible_host': '192.0.2.100'}},
                  vault_logging_admin_password='placeholder-password-' + 'x' * 32,
                  vault_logging_garage_rpc_secret='a' * 64,
                  vault_logging_s3_access_key='GK' + 'b' * 24,
                  vault_logging_s3_secret_key='c' * 64,
                  vault_logging_oidc_client_id='placeholder-client',
                  vault_logging_oidc_client_secret='placeholder-secret-' + 'x' * 32)
    values.update(overrides)
    for _ in range(5):
        values = {k: env.from_string(v).render(values) if isinstance(v, str) and '{{' in v else v
                  for k, v in values.items()}
    return env.from_string((ROOT / 'roles' / role / 'templates' / name).read_text()).render(values)


class LoggingTests(unittest.TestCase):
    def test_nas_collectors_verify_distinct_certificates_without_published_ports(self):
        devices = [{'name': 'files', 'address': '192.0.2.3'},
                   {'name': 'games', 'address': '192.0.2.4'}]
        services = yaml.safe_load(render('logging', 'compose.yaml.j2', logging_unas_enabled=True,
                                         logging_unas_devices=devices))['services']
        for device in devices:
            collector = services['unas-' + device['name']]
            self.assertNotIn('ports', collector)
            self.assertEqual(collector['extra_hosts'], ['unifi.local:' + device['address']])
            self.assertIn('./config/unas-' + device['name'] + '.crt:/etc/unpoller/controller.crt:ro',
                          collector['volumes'])
        environment = render('logging', 'unas.env.j2', logging_unas_username='fixture',
                             logging_unas_password='placeholder')
        self.assertIn('UP_UNIFI_DISABLE=true', environment)
        self.assertIn('UP_UNAS_DEVICE_0_VERIFY_SSL=true', environment)

    def test_metrics_are_private_and_optional_unifi_is_scraped(self):
        for enabled in [False, True]:
            document = yaml.safe_load(render('logging', 'compose.yaml.j2', logging_unifi_enabled=enabled))
            services = document['services']
            self.assertEqual(services['prometheus']['ports'], ['127.0.0.1:19090:9090'])
            self.assertNotIn('labels', services['prometheus'])
            self.assertEqual('unpoller' in services, enabled)
            config = yaml.safe_load(render('logging', 'prometheus.yaml.j2', logging_unifi_enabled=enabled))
            jobs = {job['job_name']: job for job in config['scrape_configs']}
            self.assertEqual('unifi' in jobs, enabled)
            self.assertEqual(jobs['vllm']['static_configs'][0]['targets'], ['192.0.2.100:11438'])
            if enabled:
                self.assertNotIn('ports', services['unpoller'])
                self.assertIn('UP_UNIFI_CONTROLLER_0_VERIFY_SSL=true',
                              render('logging', 'unpoller.env.j2', logging_unifi_password='placeholder'))

    def test_query_audit_records_cannot_satisfy_host_heartbeat(self):
        spec = importlib.util.spec_from_file_location('logging_checks', ROOT / 'roles/logging/files/checks.py')
        checks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checks)

        def response(url, **_):
            if url.endswith('/api/v1/targets'):
                return io.BytesIO(json.dumps({'data': {'activeTargets': [
                    {'health': 'up', 'labels': {'job': 'fixture'}}]}}).encode())
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['query'][0]
            # The only ingested record is Loki's own Docker query audit log.
            # A selector restricted to system/heartbeat must reject that record.
            results = [] if 'job=~"system|heartbeat"' in query else [{'stream': {'job': 'docker'}}]
            return io.BytesIO(json.dumps({'data': {'result': results}}).encode())

        with patch.dict(os.environ, {'NAS_SERVER': '192.0.2.3', 'NAS_WARNING_PERCENT': '85',
                                     'EXPECTED_HOSTS': '["offline-host"]', 'HEARTBEAT_MAX_AGE': '15m'}), \
                patch.object(checks.socket, 'create_connection'), \
                patch.object(checks.os, 'statvfs') as disk, \
                patch.object(checks.Path, 'stat') as stat, \
                patch.object(checks.urllib.request, 'urlopen', side_effect=response):
            disk.return_value.f_bavail = 90
            disk.return_value.f_blocks = 100
            stat.return_value.st_mtime = checks.time.time()
            self.assertEqual(checks.check(), ['No recent heartbeat from offline-host'])

    def test_ninety_day_retention_and_local_recovery_state(self):
        loki = yaml.safe_load(render('logging', 'loki.yaml.j2'))
        self.assertEqual(loki['limits_config']['retention_period'], '2160h')
        self.assertTrue(loki['compactor']['retention_enabled'])
        self.assertEqual(loki['compactor']['delete_request_store'], 's3')
        self.assertEqual(loki['storage_config']['aws']['endpoint'], 'logging-garage:3900')
        self.assertEqual(loki['ingester']['wal']['dir'], '/var/lib/loki/wal')

    def test_private_ingestion_and_native_oidc_browser_access(self):
        document = yaml.safe_load(render('logging', 'compose.yaml.j2'))
        services = document['services']
        self.assertEqual(services['loki']['ports'], ['127.0.0.1:13100:3100'])
        self.assertEqual(services['gateway']['ports'], ['192.0.2.6:13443:8443'])
        self.assertNotIn('ports', services['garage'])
        self.assertNotIn('ports', services['grafana'])
        self.assertNotIn('traefik.http.routers.logging.middlewares', services['grafana']['labels'])
        self.assertTrue(document['networks']['default']['internal'])
        self.assertIn('ingress', services['loki']['networks'])
        self.assertIn('ingress', services['gateway']['networks'])
        self.assertEqual(services['garage']['networks'], ['default'])
        gateway = render('logging', 'nginx.conf.j2')
        self.assertIn('ssl_verify_client on;', gateway)
        self.assertIn('limit_except POST { deny all; }', gateway)
        self.assertNotIn('/query', gateway)
        grafana = configparser.ConfigParser()
        grafana.read_string(render('logging', 'grafana.ini.j2'))
        self.assertEqual(grafana['auth.proxy']['enabled'], 'false')
        self.assertEqual(grafana['auth.anonymous']['enabled'], 'false')
        oidc = grafana['auth.generic_oauth']
        self.assertEqual(oidc['enabled'], 'true')
        self.assertEqual(oidc['use_pkce'], 'true')
        self.assertEqual(oidc['validate_id_token'], 'true')
        self.assertEqual(oidc['allowed_groups'], 'sysadmins')
        self.assertEqual(oidc['role_attribute_strict'], 'true')
        self.assertNotIn('placeholder-secret', render('logging', 'grafana.ini.j2'))

    def test_nas_data_cannot_silently_fall_back_to_root_disk(self):
        document = yaml.safe_load(render('logging', 'compose.yaml.j2'))
        data = next(v for v in document['services']['garage']['volumes'] if isinstance(v, dict))
        self.assertEqual(data['source'], '/mnt/nas/logging/Logs/garage')
        self.assertFalse(data['bind']['create_host_path'])
        tasks = yaml.safe_load((ROOT / 'roles/logging/tasks/main.yml').read_text())
        guard = next(i for i, t in enumerate(tasks) if t['name'].startswith('Verify logging storage'))
        compose = next(i for i, t in enumerate(tasks) if 'community.docker.docker_compose_v2' in t)
        self.assertLess(guard, compose)

    def test_linux_and_native_mac_collection_have_persistent_buffers(self):
        mac_values = {'ansible_facts': {'os_family': 'Darwin'}, 'inventory_hostname': 'mac-mini',
                      'ansible_user_dir': '/Users/test'}
        for family in ['Debian', 'Darwin']:
            document = yaml.safe_load(render('vector', 'vector.yaml.j2', ansible_facts={'os_family': family}))
            self.assertEqual('containers' in document['sources'], family == 'Debian')
            self.assertEqual('journal' in document['sources'], family == 'Debian')
            sink = document['sinks']['archive']
            self.assertEqual(sink['buffer'], {'type': 'disk', 'max_size': 10737418240, 'when_full': 'block'})
            self.assertTrue(sink['tls']['verify_certificate'])
            self.assertTrue(sink['tls']['verify_hostname'])
        plist = plistlib.loads(render('vector', 'launchd.plist.j2', **mac_values).encode())
        self.assertIn('/Users/test/.local/share/homelab-vector/vector.yaml', plist['ProgramArguments'])
        plistlib.loads(render('vector', 'heartbeat.plist.j2', **mac_values).encode())


def validate_configs():
    with tempfile.TemporaryDirectory(prefix='homelab-logging-config-') as temp:
        root = Path(temp)
        loki = root / 'loki.yaml'
        loki.write_text(render('logging', 'loki.yaml.j2'))
        subprocess.run(['docker', 'run', '--rm', '-v', f'{loki}:/etc/loki/config.yaml:ro',
                        '-e', 'LOKI_S3_ACCESS_KEY=placeholder', '-e', 'LOKI_S3_SECRET_KEY=placeholder',
                        'grafana/loki:3.7.9', '-config.file=/etc/loki/config.yaml',
                        '-config.expand-env=true', '-verify-config=true'], check=True)
        prometheus = root / 'prometheus.yaml'
        prometheus.write_text(render('logging', 'prometheus.yaml.j2', logging_unifi_enabled=True))
        subprocess.run(['docker', 'run', '--rm', '--entrypoint', '/bin/promtool',
                        '-v', f'{prometheus}:/etc/prometheus/config.yaml:ro',
                        'prom/prometheus:v3.15.1', 'check', 'config', '/etc/prometheus/config.yaml'], check=True)
        for family in ['Debian', 'Darwin']:
            file = root / (family + '.yaml')
            document = yaml.safe_load(render('vector', 'vector.yaml.j2', ansible_facts={'os_family': family}))
            document['tests'] = []
            for name, path, message, expected in [
                    ('traefik event time', '/host/traefik/access.log',
                     '{"StartUTC":"2026-10-28T10:00:00Z"}', "2026-10-28T10:00:00Z"),
                    ('unparsed access record', '/host/traefik/access.log',
                     'older common format line', '2026-10-28T11:00:00Z'),
                    ('other application file', '/host/other.log',
                     '{"StartUTC":"2026-10-28T10:00:00Z"}', '2026-10-28T11:00:00Z')]:
                document['tests'].append({
                    'name': name,
                    'inputs': [{'insert_at': 'normalize', 'type': 'log', 'log_fields': {
                        'file': path, 'message': message, 'timestamp': '2026-10-28T11:00:00Z'}}],
                    'outputs': [{'extract_from': 'normalize', 'conditions': [{'type': 'vrl',
                        'source': f"assert_eq!(.timestamp, t'{expected}')"}]}]})
            # Test events carry typed timestamps, as real file events do.
            for test in document['tests']:
                fields = test['inputs'][0].pop('log_fields')
                test['inputs'][0].update(type='vrl', source=(
                    f'.file = {json.dumps(fields["file"])}\n.message = {json.dumps(fields["message"])}\n'
                    ".timestamp = t'2026-10-28T11:00:00Z'"))
            file.write_text(yaml.safe_dump(document))
            subprocess.run(['docker', 'run', '--rm', '-v', f'{file}:/etc/vector/vector.yaml:ro',
                            'timberio/vector:0.60.0-debian', 'validate', '--no-environment',
                            '/etc/vector/vector.yaml'], check=True)
            subprocess.run(['docker', 'run', '--rm', '-v', f'{file}:/etc/vector/vector.yaml:ro',
                            'timberio/vector:0.60.0-debian', 'test', '/etc/vector/vector.yaml'], check=True)
    print('PASS: Loki, Prometheus and both Vector configurations validated by pinned binaries')


if __name__ == '__main__':
    if '--validate-configs' in sys.argv:
        validate_configs()
    else:
        unittest.main()
