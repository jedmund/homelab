#!/usr/bin/env python3
"""Check end-to-end collection, NAS capacity, and consistent metadata backups."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import threading
import time
import urllib.parse
import urllib.request

STATE = {'checked_at': 0, 'errors': ['Initial collection check pending']}


def check():
    errors = []
    try:
        with socket.create_connection((os.environ['NAS_SERVER'], 2049), timeout=3):
            pass
        disk = os.statvfs('/nas')
        used = 100 * (1 - disk.f_bavail / disk.f_blocks)
        if used >= int(os.environ['NAS_WARNING_PERCENT']):
            errors.append(f'NAS usage {used:.1f}% exceeds threshold')
    except Exception:
        errors.append('NAS unavailable')
    for host in json.loads(os.environ['EXPECTED_HOSTS']):
        # Exclude Docker output: Loki's own query logs contain this search
        # string and must never satisfy the collection heartbeat check.
        query = '{host=' + json.dumps(host) + ',collector="vector",job=~"system|heartbeat"} |= "homelab-log-heartbeat"'
        parameters = urllib.parse.urlencode({'query': query, 'since': os.environ['HEARTBEAT_MAX_AGE'], 'limit': 1})
        try:
            with urllib.request.urlopen('http://logging-loki:3100/loki/api/v1/query_range?' + parameters, timeout=10) as response:
                result = json.load(response)
            if not result.get('data', {}).get('result'):
                errors.append('No recent heartbeat from ' + host)
        except Exception:
            errors.append('Unable to query heartbeat for ' + host)
    try:
        if time.time() - Path('/backup/snapshot.ok').stat().st_mtime > 27 * 3600:
            errors.append('Metadata snapshots are older than 27 hours')
    except OSError:
        errors.append('Metadata snapshot missing')
    try:
        with urllib.request.urlopen('http://logging-prometheus:9090/api/v1/targets', timeout=10) as response:
            targets = json.load(response)['data']['activeTargets']
        if not targets:
            errors.append('Prometheus has no scrape targets')
        for target in targets:
            if target['health'] != 'up':
                errors.append('Metrics unavailable for ' + target['labels']['job'])
        expected_unas = json.loads(os.environ.get('EXPECTED_UNAS', '[]'))
        if expected_unas:
            query = urllib.parse.urlencode({'query': 'count by(host)(unpoller_unas_pool_capacity_bytes)'})
            with urllib.request.urlopen('http://logging-prometheus:9090/api/v1/query?' + query, timeout=10) as response:
                results = json.load(response)['data']['result']
            reporting = {entry['metric']['host'] for entry in results}
            for name in expected_unas:
                if 'unas-' + name not in reporting:
                    errors.append('Storage telemetry unavailable for UNAS ' + name)
    except Exception:
        errors.append('Unable to query Prometheus scrape health')
    return errors


def monitor():
    while True:
        errors = check()
        STATE.update(checked_at=time.time(), errors=errors)
        time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            try:
                data = Path('/backup-metrics/backup.prom').read_text()
                data += 'homelab_backup_exporter_available 1\n'
            except OSError:
                data = 'homelab_backup_exporter_available 0\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(data.encode())
            return
        if self.path == '/live':
            errors = []
        elif self.path == '/health':
            errors = list(STATE['errors'])
            if time.time() - STATE['checked_at'] > 180:
                errors.append('Collection check stalled')
        else:
            self.send_error(404)
            return
        self.send_response(503 if errors else 200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'ok': not errors, 'errors': errors}).encode())

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    threading.Thread(target=monitor, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
