#!/usr/bin/env python3
"""Real pinned router/socket-proxy smoke test against disposable backends.

DOCKER_HOST=ssh://max python3 tests/test_minecraft_routing.py max
The positional SSH host is used only for loopback TCP probes.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

import yaml
from test_minecraft import render

PROBE = '''import json, socket, struct, sys
port, host, mode = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
def varint(n):
    result = b''
    while n > 127:
        result += bytes([(n & 127) | 128]); n >>= 7
    return result + bytes([n])
def readvar(s):
    value = 0
    for shift in range(0, 35, 7):
        b = s.recv(1)
        if not b: raise EOFError()
        value |= (b[0] & 127) << shift
        if b[0] < 128: return value
    raise ValueError()
s = socket.create_connection(('127.0.0.1', port), timeout=8)
body = b'\\x00' + varint(767) + varint(len(host)) + host.encode() + struct.pack('>H',25565) + varint(mode)
s.sendall(varint(len(body)) + body)
if mode == 1:
    s.sendall(b'\\x01\\x00')
    try:
        readvar(s); readvar(s); size=readvar(s); data=b''
        while len(data) < size:
            chunk=s.recv(size-len(data))
            if not chunk: raise EOFError()
            data+=chunk
        print(data.decode())
    except EOFError:
        print('REJECTED')
else:
    name=b'FixturePlayer'
    body=b'\\x00'+varint(len(name))+name+bytes(16)
    s.sendall(varint(len(body))+body)
    import time; time.sleep(2)
s.close()
'''


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout


def main():
    host = sys.argv[1]
    project = 'mc-routing-' + uuid.uuid4().hex[:8]
    document = yaml.safe_load(render('compose.yaml.j2', logging_driver='json-file',
                                    logging_max_size='10m', logging_max_file='3'))
    document['name'] = project
    document['networks'] = {'minecraft': {'name': project + '-game'},
                            'control': {'internal': True}}
    for name, svc in document['services'].items():
        svc['container_name'] = project + '-' + name
        if name in ('sky', 'atm10', 'vanilla'):
            svc['image'] = 'alpine:3.20'
            svc['entrypoint'] = ['sleep', '3600']
            svc.pop('env_file')
            svc.pop('volumes')
            svc['labels']['mc-router.host'] = name + '.' + project + '.invalid'
            svc['labels']['mc-router.network'] = project + '-game'
        if name == 'router':
            svc['ports'] = ['127.0.0.1::25565']
    with tempfile.TemporaryDirectory(prefix=project) as tmp:
        path = Path(tmp) / 'compose.yaml'
        path.write_text(yaml.safe_dump(document))

        def compose(*args):
            return run('docker', 'compose', '-f', str(path), *args)

        def state(name):
            return json.loads(run('docker', 'inspect', project + '-' + name))[0]['State']['Running']

        def probe(name, mode=1):
            port = compose('port', 'router', '25565').strip().rsplit(':', 1)[1]
            return run('ssh', host, 'python3', '-', port, name, str(mode), input=PROBE)

        try:
            compose('--profile', 'backends', 'create', 'sky', 'atm10', 'vanilla')
            compose('up', '-d', 'socket-proxy', 'router')
            time.sleep(5)
            for name in ('sky', 'atm10', 'vanilla'):
                reply = probe(name + '.' + project + '.invalid')
                assert 'Sleeping' in reply, reply
                assert not state(name), 'status poll woke backend'
            assert 'REJECTED' in probe('unknown.' + project + '.invalid')
            probe('sky.' + project + '.invalid', 2)
            assert state('sky'), 'join failed to wake selected backend'
            assert not state('atm10') and not state('vanilla')
            assert 'Loading' in probe('sky.' + project + '.invalid')
            print('PASS sleeping/loading MOTD, status without wake, unknown rejection, selected wake')
        except Exception:
            print(compose('logs', '--tail', '40', 'router', 'socket-proxy'), file=sys.stderr)
            raise
        finally:
            compose('--profile', 'backends', 'down', '--volumes', '--timeout', '1')


if __name__ == '__main__':
    main()
