#!/usr/bin/env python3
"""Opt-in deployment test: disposable canaries and logging-service restarts only.

Run after deploying the backend and max collector. No application data is mounted.
"""
import argparse
import json
import shlex
import subprocess
import time
import uuid


def ssh(host, *argv, input=None):
    command = shlex.join(argv)
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', host, command],
                          input=input, text=True, capture_output=True, check=True).stdout


def query(backend, marker, host):
    selector = '{host=' + json.dumps(host) + ',collector="vector",job="docker",container=' + json.dumps(marker.rsplit('-', 1)[0]) + '}'
    code = '''import json,urllib.parse,urllib.request
q=''' + repr(selector + ' |= ' + json.dumps(marker)) + '''
marker=''' + repr(marker) + '''
url='http://127.0.0.1:13100/loki/api/v1/query_range?'+urllib.parse.urlencode({'query':q,'since':'1h','limit':20})
with urllib.request.urlopen(url,timeout=10) as r: x=json.load(r)
print(sum(line.strip() == marker for s in x.get('data',{}).get('result',[]) for _,line in s['values']))
'''
    return int(ssh(backend, 'python3', '-', input=code).strip())


def wait_for(backend, marker, host, timeout=90):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if query(backend, marker, host):
                return
        except subprocess.CalledProcessError:
            pass
        time.sleep(2)
    raise AssertionError('Canary not found: ' + marker)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='nuc')
    parser.add_argument('--collector', default='max')
    parser.add_argument('--host-label', default='max')
    args = parser.parse_args()
    name = 'homelab-log-canary-' + uuid.uuid4().hex[:10]
    markers = [name + '-' + stage for stage in ['original', 'replacement', 'outage']]
    stopped = False
    try:
        for i, marker in enumerate(markers):
            if i:
                ssh(args.collector, 'docker', 'rm', '-f', name)
            if i == 2:
                ssh(args.backend, 'docker', 'stop', '--time', '10', 'logging-gateway')
                stopped = True
            ssh(args.collector, 'docker', 'run', '-d', '--name', name, '--network', 'none',
                'alpine:3.20', 'sh', '-c', 'echo ' + marker + '; sleep 240')
            if i < 2:
                wait_for(args.backend, marker, args.host_label)
            else:
                time.sleep(10)
                assert query(args.backend, marker, args.host_label) == 0, 'Stopped ingress unexpectedly delivered marker'
                # Remove the source before restarting: recovery must use the
                # persistent collector buffer, not reread the Docker log.
                ssh(args.collector, 'docker', 'rm', '-f', name)
                ssh(args.collector, 'docker', 'restart', '--time', '30', 'vector')
                ssh(args.backend, 'docker', 'start', 'logging-gateway')
                stopped = False
                wait_for(args.backend, marker, args.host_label)
        for marker in markers:
            wait_for(args.backend, marker, args.host_label)
        ssh(args.backend, 'docker', 'restart', '--time', '30', 'logging-loki')
        for marker in markers:
            wait_for(args.backend, marker, args.host_label)
        print('PASS: canary logs survive source deletion/replacement, ingestion outage, collector restart, and Loki restart')
        print('Canary prefix:', name)
    finally:
        if stopped:
            ssh(args.backend, 'docker', 'start', 'logging-gateway')
        subprocess.run(['ssh', args.collector, shlex.join(['docker', 'rm', '-f', name])],
                       capture_output=True, check=False)


if __name__ == '__main__':
    main()
