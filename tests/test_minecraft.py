#!/usr/bin/env python3
"""Exercise snapshot failure handling using disposable data and Docker state."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import time

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = yaml.safe_load((ROOT / 'roles/minecraft/defaults/main.yml').read_text())


def render(name, **values):
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.filters['to_json'] = json.dumps
    return env.from_string((ROOT / 'roles/minecraft/templates' / name).read_text()).render(
        ansible_managed='fixture', **(DEFAULTS | values))


class Snapshots(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        module = self.root / 'snapshot.py'
        module.write_text(render('snapshot.py.j2', minecraft_snapshot_root=str(self.root / 'copies'),
                                 config_base=str(self.root / 'source')))
        spec = importlib.util.spec_from_file_location('snapshot', module)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.m.LOCK = self.root / 'lock'
        self.m.SOURCE.mkdir()
        (self.m.SOURCE / 'env').mkdir()
        (self.m.SOURCE / 'compose.yaml').write_text('original compose')
        for name in self.m.SERVERS:
            data = self.m.SOURCE / name / 'data'
            data.mkdir(parents=True)
            (data / 'world').mkdir()
            (data / 'world/level.dat').write_text('world-' + name)
            (data / 'logs').mkdir()
            (data / 'logs/latest.log').write_text('log')
        self.states = {'minecraft-router': 'running'}
        self.events = []
        self.real_run = self.m.run
        self.fail_copy = False
        self.race = False

    def run_command(self, *args, **kwargs):
        if args[0] == 'docker':
            self.events.append(args[1])
            self.states['minecraft-router'] = 'exited' if args[1] == 'stop' else 'running'
            if self.race and args[1] == 'stop':
                self.states['minecraft-sky'] = 'running'
            return
        if self.fail_copy:
            raise subprocess.TimeoutExpired(args, 1)
        return self.real_run(*args, **kwargs)

    def snapshot(self, baseline=False, force=False):
        with patch.object(self.m, 'state', side_effect=lambda n: self.states.get(n, 'exited')), \
             patch.object(self.m, 'run', side_effect=self.run_command):
            self.m.snapshot(baseline, force=force)

    def test_stopped_snapshot_excludes_logs_and_recovers_router(self):
        self.snapshot()
        self.assertEqual(self.events, ['stop', 'start'])
        self.assertTrue((self.m.ROOT / 'current/sky/data/world/level.dat').exists())
        self.assertFalse((self.m.ROOT / 'current/sky/data/logs').exists())
        self.snapshot()
        self.assertEqual(self.events, ['stop', 'start'])

    def test_explicit_refresh_keeps_idle_guard(self):
        self.snapshot()
        previous = (self.m.ROOT / 'current').resolve()
        self.snapshot(force=True)
        self.assertNotEqual((self.m.ROOT / 'current').resolve(), previous)
        self.states['minecraft-sky'] = 'running'
        previous = (self.m.ROOT / 'current').resolve()
        self.snapshot(force=True)
        self.assertEqual((self.m.ROOT / 'current').resolve(), previous)

    def test_awake_defers_without_stopping_router(self):
        self.states['minecraft-sky'] = 'running'
        self.snapshot()
        self.assertEqual(self.events, [])
        self.assertFalse((self.m.ROOT / 'current').exists())

    def test_concurrent_wake_defers_and_restores_router(self):
        self.race = True
        self.snapshot()
        self.assertEqual(self.events, ['stop', 'start'])
        self.assertFalse((self.m.ROOT / 'current').exists())

    def test_copy_timeout_keeps_previous_and_recovers(self):
        self.snapshot()
        previous = (self.m.ROOT / 'current').resolve()
        (previous / 'snapshot-time').write_text(str(int(time.time()) - 90000))
        self.fail_copy = True
        with self.assertRaises(subprocess.TimeoutExpired):
            self.snapshot()
        self.assertEqual((self.m.ROOT / 'current').resolve(), previous)
        self.assertEqual(self.states['minecraft-router'], 'running')
        self.assertFalse(self.m.LOCK.exists())
        self.assertFalse(list(self.m.ROOT.glob('.partial-*')))

    def test_maintenance_lock_excludes_snapshot(self):
        self.m.LOCK.mkdir()
        with self.assertRaises(FileExistsError):
            self.snapshot()
        self.assertEqual(self.events, [])

    def test_baseline_retains_full_directories(self):
        self.snapshot(baseline=True)
        self.assertTrue((self.m.ROOT / 'baseline/sky/data/logs/latest.log').exists())
        self.assertTrue((self.m.ROOT / 'baseline/compose.yaml').exists())

    def test_systemd_recovery_restores_router_and_removes_dead_owner_lock(self):
        self.m.ROOT.mkdir()
        (self.m.ROOT / 'router-recovery').touch()
        self.m.LOCK.mkdir()
        (self.m.LOCK / 'owner').write_text('99999999')
        with patch.object(self.m, 'run', side_effect=self.run_command), \
             patch.object(self.m.os, 'kill', side_effect=ProcessLookupError):
            self.m.recover()
        self.assertEqual(self.events, ['start'])
        self.assertFalse(self.m.LOCK.exists())
        self.assertFalse((self.m.ROOT / 'router-recovery').exists())

    def test_missing_world_rejected(self):
        result = subprocess.run(['python3', str(ROOT / 'roles/minecraft/files/validate-data.py'),
                                 str(self.m.SOURCE)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)


class Compose(unittest.TestCase):
    def test_render(self):
        document = yaml.safe_load(render('compose.yaml.j2', logging_driver='json-file',
                                        logging_max_size='10m', logging_max_file='3'))
        services = document['services']
        self.assertEqual([name for name, svc in services.items() if 'ports' in svc], ['router'])
        for name in ('sky', 'atm10', 'vanilla'):
            self.assertEqual(services[name]['restart'], 'no')
            self.assertEqual(services[name]['environment']['INIT_MEMORY'], '1G')
        self.assertEqual(services['socket-proxy']['environment']['POST'], '0')
        self.assertNotIn('volumes', services['router'])


if __name__ == '__main__':
    unittest.main()
