#!/usr/bin/env python3
"""Disposable real-Docker state fixtures; set DOCKER_HOST, e.g. ssh://max.

Uses the production Compose template and reconciliation service selection,
with tiny sleep processes instead of game servers. No production data is mounted.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

import yaml
from test_minecraft import render


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main():
    project = 'mc-fixture-' + uuid.uuid4().hex[:10]
    document = yaml.safe_load(render('compose.yaml.j2', logging_driver='json-file',
                                    logging_max_size='10m', logging_max_file='3'))
    document['name'] = project
    document['networks'] = {'minecraft': {}, 'control': {'internal': True}}
    for name, service in document['services'].items():
        service['container_name'] = project + '-' + name
        service.pop('ports', None)
        service.pop('env_file', None)
        service.pop('volumes', None)
        service.pop('read_only', None)
        service.pop('tmpfs', None)
        service['image'] = 'alpine:3.20'
        service['entrypoint'] = ['/bin/sh', '-c', 'trap "exit 0" TERM; while :; do sleep 1 & wait $!; done']
        service.pop('labels', None)
    with tempfile.TemporaryDirectory(prefix=project) as tmp:
        path = Path(tmp) / 'compose.yaml'
        path.write_text(yaml.safe_dump(document))

        def compose(*args):
            return run('docker', 'compose', '-f', str(path), *args)

        def inspect(name):
            return json.loads(run('docker', 'inspect', project + '-' + name))[0]

        def reconcile():
            awake = []
            for name in ('sky', 'atm10', 'vanilla'):
                result = subprocess.run(['docker', 'inspect', project + '-' + name], capture_output=True)
                if result.returncode == 0 and json.loads(result.stdout)[0]['State']['Running']:
                    awake.append(name)
                else:
                    compose('--profile', 'backends', 'create', '--pull', 'missing', name)
            compose('up', '-d', 'socket-proxy', 'router', *awake)

        def identities():
            return {n: (inspect(n)['Id'], inspect(n)['State']['Running'])
                    for n in document['services']}

        try:
            reconcile()
            before = identities()
            assert all(not before[n][1] for n in ('sky', 'atm10', 'vanilla'))
            reconcile()
            assert identities() == before, 'unchanged sleeping deployment changed identity/state'
            run('docker', 'start', project + '-sky')
            before = identities()
            reconcile()
            assert identities() == before, 'mixed deployment changed identity/state'
            document['services']['atm10']['environment']['FIXTURE_CHANGE'] = '1'
            document['services']['sky']['environment']['FIXTURE_CHANGE'] = '1'
            path.write_text(yaml.safe_dump(document))
            reconcile()
            after = identities()
            assert after['sky'][0] != before['sky'][0] and after['sky'][1]
            assert after['atm10'][0] != before['atm10'][0] and not after['atm10'][1]
            assert after['vanilla'] == before['vanilla']
            # Simulate the stopped backend state left by a host reboot, without rebooting a host.
            compose('--profile', 'backends', 'stop')
            compose('up', '-d')
            assert all(not inspect(n)['State']['Running'] for n in ('sky', 'atm10', 'vanilla'))
            print('PASS first deployment, unchanged identity, mixed states, changes, simulated boot')
        finally:
            compose('--profile', 'backends', 'down', '--volumes')


if __name__ == '__main__':
    main()
