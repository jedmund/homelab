#!/usr/bin/env python3
"""Exercise repository Compose tasks against disposable local containers.

Requires Ansible, PyYAML, and a local Docker Unix socket. No inventory or vaults
are loaded. Production build/deploy expressions are imported, not reimplemented.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = 'community.docker.docker_compose_v2'
BUILD_ROLES = ('line', 'backup', 'matrix', 'strudel', 'petlibro', 'musicbrainz')


def run(argv, **kwargs):
    return subprocess.run(argv, text=True, capture_output=True, **kwargs)


def require(argv, **kwargs):
    result = run(argv, **kwargs)
    if result.returncode:
        raise AssertionError(f'{argv}:\n{result.stdout}\n{result.stderr}')
    return result.stdout.strip()


def tasks(items):
    for item in items or []:
        if isinstance(item, dict):
            yield item
            for key in ('block', 'rescue', 'always'):
                yield from tasks(item.get(key, []))


def static_checks():
    """Check actual task reachability and ordering across every product role."""
    for role in (ROOT / 'roles').iterdir():
        all_tasks = []
        handlers = []
        for path in (role / 'tasks').glob('*.yml'):
            all_tasks += list(tasks(yaml.safe_load(path.read_text())))
        for path in (role / 'handlers').glob('*.yml'):
            handlers += list(tasks(yaml.safe_load(path.read_text())))
        assert not any(COMPOSE in h for h in handlers), role.name
        allowed = {h['name'] for h in handlers}
        allowed |= {h['listen'] for h in handlers if isinstance(h.get('listen'), str)}
        for task in all_tasks:
            notify = task.get('notify', [])
            for listener in [notify] if isinstance(notify, str) else notify:
                assert listener in allowed, (role.name, task['name'], listener)
        for i, task in enumerate(all_tasks):
            if COMPOSE not in task:
                continue
            flags = re.findall(r'\b([a-z_]+)\.changed', task[COMPOSE].get('recreate', ''))
            prior = {t.get('register') for t in all_tasks[:i]}
            assert set(flags) <= prior, (role.name, set(flags) - prior)
    for role in BUILD_ROLES:
        main = yaml.safe_load((ROOT / 'roles' / role / 'tasks/main.yml').read_text())
        project = next(t[COMPOSE]['project_src'] for t in main if COMPOSE in t)
        build = yaml.safe_load((ROOT / 'roles' / role / 'tasks/build.yml').read_text())
        config = next(t for t in tasks(build) if t['name'] == 'Read effective Compose configuration')
        assert config['ansible.builtin.command']['chdir'] == project, role
        record = next(t for t in main if t['name'].startswith('Record successful '))
        assert record['ansible.builtin.copy']['dest'] == project + '/.ansible-build-inputs.json', role
    print('PASS: handler references and recreation ordering across all roles', flush=True)


def decision_checks(root, env):
    """Evaluate the real expressions with absent, skipped, and changed results."""
    checks = []
    for role in sorted((ROOT / 'roles').iterdir()):
        path = role / 'tasks/main.yml'
        if not path.exists():
            continue
        for task in tasks(yaml.safe_load(path.read_text())):
            if COMPOSE not in task or 'recreate' not in task[COMPOSE]:
                continue
            expression = task[COMPOSE]['recreate']
            flags = re.findall(r'\b([a-z_]+)\.changed', expression)
            cases = [('undefined', {}, 'auto'),
                     ('skipped', {f: {'skipped': True, 'changed': False} for f in flags}, 'auto')]
            for flag in flags:
                values = {f: {'changed': False} for f in flags}
                values[flag] = {'changed': True, 'results': [{'changed': False}, {'changed': True}]}
                cases.append((flag, values, 'always'))
            for label, values, expected in cases:
                checks.append({'name': f'{role.name}: {label}', 'vars': values,
                               'ansible.builtin.set_fact': {'fixture_decision': expression}})
                checks.append({'name': f'Check {role.name} decision',
                               'ansible.builtin.assert': {'that': f'fixture_decision == "{expected}"'}})
    file = root / 'decisions.yml'
    file.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local',
                                   'gather_facts': False, 'tasks': checks}], sort_keys=False))
    result = run(['ansible-playbook', '-i', 'localhost,', str(file)], env=env)
    (root / 'decisions.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, f'Recreation decisions failed: {root / "decisions.log"}'
    print(f'PASS: {len(checks) // 2} recreation decisions from actual role expressions', flush=True)


def template_checks(root, env, docker):
    """Validate real mixed/local-image templates, including both catbro modes."""
    common = yaml.safe_load((ROOT / 'group_vars/compute_servers/common.yml').read_text())
    common.update(yaml.safe_load((ROOT / 'group_vars/compute_servers/docker.yml').read_text()))
    checks = []
    outputs = []
    for role in ('line', 'backup', 'matrix', 'strudel', 'petlibro'):
        defaults = yaml.safe_load((ROOT / 'roles' / role / 'defaults/main.yml').read_text())
        for enabled in ([False, True] if role == 'petlibro' else [False]):
            file = root / f'{role}-{enabled}.yaml'
            values = common | defaults | {'docker_base_path': str(root), 'petlibro_catbro_enabled': enabled}
            checks.append({'name': f'Render {role} template', 'vars': values,
                           'ansible.builtin.template': {'src': str(ROOT / 'roles' / role / 'templates/compose.yaml.j2'),
                                                      'dest': str(file), 'mode': '0600'}})
            outputs.append((role, enabled, file))
    file = root / 'templates.yml'
    file.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
                                   'vars': {'ansible_python_interpreter': sys.executable}, 'tasks': checks}], sort_keys=False))
    result = run(['ansible-playbook', '-i', 'localhost,', str(file)], env=env)
    (root / 'templates.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, f'Template rendering failed: {root / "templates.log"}'
    for role, enabled, file in outputs:
        require([docker, 'compose', '-f', str(file), 'config', '--no-env-resolution', '--quiet'], env=env)
        services = yaml.safe_load(file.read_text())['services']
        if role == 'petlibro':
            assert ('catbro' in services) == enabled
        for service in services.values():
            if 'build' in service:
                assert service['pull_policy'] == 'build', (role, service)
            else:
                assert service['pull_policy'] == ('missing' if role == 'petlibro' else 'always'), role
    print('PASS: six rendered production Compose configurations and image pull policies', flush=True)


class Fixture:
    def __init__(self, root, role, docker, env, base):
        self.role = role
        self.name = f'hl-compose-test-{role.replace("_", "-")}-{uuid.uuid4().hex[:8]}'
        self.path = root / self.name
        self.path.mkdir()
        self.docker = docker
        self.env = env
        self.base = base
        self.is_build = role in BUILD_ROLES
        self.images = [f'{self.name}:local']
        self.log = self.path / 'docker-calls.jsonl'
        self.wrapper = self.path / 'bin'
        self.wrapper.mkdir()
        exe = self.wrapper / 'docker'
        exe.write_text(f'#!{sys.executable}\nimport json,os,sys\n'
                       f'with open({str(self.log)!r}, "a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                       f'os.execv({docker!r}, [{docker!r}, *sys.argv[1:]])\n')
        exe.chmod(0o755)
        self.env = dict(env, PATH=f'{self.wrapper}{os.pathsep}{env["PATH"]}')
        self.main = yaml.safe_load((ROOT / 'roles' / role / 'tasks/main.yml').read_text())
        self.apply = copy.deepcopy(next(t for t in tasks(self.main) if COMPOSE in t))
        self.flags = re.findall(r'\b([a-z_]+)\.changed', self.apply[COMPOSE].get('recreate', ''))
        self.vars = {
            'stack_name': self.name, 'config_base': str(self.path),
            'docker_base_path': str(root), 'ansible_user': os.environ['USER'],
            'ansible_python_interpreter': sys.executable,
            'musicbrainz_upstream_path': str(self.path), 'musicbrainz_merged_compose_path': 'compose.yaml',
            'docker_pull_policy': 'missing', f'{role}_force_rebuild': False,
            'line_git': {'after': 'revision-1'}, 'catbro_git': {'after': 'revision-1'},
            'musicbrainz_git': {'after': 'revision-1'}, 'stash_public_without_auth': True,
        }
        self.config_version = 'one'
        self.runtime_version = 'one'
        self.enabled = True
        self.extra_build = False
        self.buildarg_version = 'one'
        self.dockerfile = self.path / 'Dockerfile'
        self.dockerfile.write_text(f'FROM {base}\nLABEL fixture.version="one"\n')
        (self.path / '.dockerignore').write_text('**\n!Dockerfile\n')
        if role == 'stash':
            (self.path / 'config').mkdir()
        self.compose()

    def compose(self):
        app = {
            'image': self.images[0] if self.is_build else self.base,
            'command': ['sleep', '3600'], 'init': True, 'stop_grace_period': '1s',
            'labels': {'fixture.version': self.config_version},
            'volumes': ['./runtime:/fixture:ro'],
            'healthcheck': {'test': ['CMD', 'test', '-f', '/fixture'], 'interval': '1s', 'timeout': '1s', 'retries': 10},
            'pull_policy': 'build' if self.is_build else 'missing',
        }
        if self.is_build:
            app['build'] = {'context': '.', 'dockerfile': 'Dockerfile', 'args': {'FIXTURE': self.buildarg_version}}
        # Include a registry-backed companion to exercise mixed-stack pull policy.
        services = {'companion': {'image': self.base, 'pull_policy': 'missing',
                                 'command': ['sleep', '3600'], 'init': True, 'stop_grace_period': '1s'}}
        if self.enabled:
            services['app'] = app
        if self.extra_build:
            # No explicit image tests Compose's project-service image naming.
            services['extra'] = {'build': {'context': '.', 'dockerfile': 'Dockerfile'},
                                 'pull_policy': 'build', 'command': ['sleep', '3600'], 'init': True, 'stop_grace_period': '1s'}
            self.images.append(f'{self.name}-extra')
        (self.path / 'compose-input.yaml').write_text(yaml.safe_dump({'name': self.name, 'services': services}))

    def state(self):
        ids = require([self.docker, 'ps', '-aq', '--filter', f'label=com.docker.compose.project={self.name}'], env=self.env)
        if not ids:
            return {}
        data = json.loads(require([self.docker, 'inspect', *ids.splitlines()], env=self.env))
        return {x['Config']['Labels']['com.docker.compose.service']: (x['Id'], x['State']['StartedAt']) for x in data}

    def execute(self, *, check=False, failure=False):
        self.compose()
        self.vars['petlibro_catbro_enabled'] = self.enabled
        # Use real register names with fixture files. The production apply and
        # build tasks below consume these results exactly as in the role.
        prepare = [
            {'name': 'Render fixture Compose', 'ansible.builtin.copy': {
                'src': str(self.path / 'compose-input.yaml'), 'dest': str(self.path / 'compose.yaml'), 'mode': '0600'}},
            {'name': 'Render fixture runtime config', 'ansible.builtin.copy': {
                'content': self.runtime_version, 'dest': str(self.path / 'runtime'), 'mode': '0644'},
             'register': self.flags[0] if self.flags else 'fixture_runtime'},
        ]
        # Leave other registers undefined to cover skipped/optional inputs.
        selected = [copy.deepcopy(t) for t in self.main if COMPOSE in t or
                    'ansible.builtin.import_tasks' in t or t['name'].startswith('Record successful ')]
        if self.role == 'musicbrainz':
            prepare = prepare[1:]
            self.vars['musicbrainz_merged_compose'] = {'stdout': (self.path / 'compose-input.yaml').read_text()}
            names = {'Reset MusicBrainz service pull policies',
                     'Preserve registry pulls without pulling local build tags', 'Write merged compose file'}
            selected = [copy.deepcopy(t) for t in self.main if t['name'] in names] + selected
        if self.role == 'stash':
            seed = next(i for i, t in enumerate(self.main) if t['name'] == 'Seed Stash config before its first start')
            selected = copy.deepcopy(self.main[seed:])
        for t in selected:
            if 'ansible.builtin.import_tasks' in t:
                t['ansible.builtin.import_tasks'] = str(ROOT / 'roles' / self.role / 'tasks' / t['ansible.builtin.import_tasks'])
            if COMPOSE in t:
                t[COMPOSE]['docker_cli'] = str(self.wrapper / 'docker')
        verify = [{'name': 'Verify runtime config after final apply', 'ansible.builtin.command': {
            'argv': ['docker', 'compose', 'exec', '-T', 'app', 'cat', '/fixture'], 'chdir': str(self.path)},
                   'register': 'fixture_seen', 'changed_when': False,
                   'when': 'not ansible_check_mode and fixture_enabled'},
                  {'name': 'Check applied contents', 'ansible.builtin.assert': {
                      'that': 'fixture_seen.stdout == fixture_runtime_version'},
                   'when': 'not ansible_check_mode and fixture_enabled'}]
        play = [{'name': 'Exercise repository deployment tasks', 'hosts': 'localhost', 'connection': 'local',
                 'gather_facts': False, 'vars': self.vars | {'fixture_enabled': self.enabled,
                     'fixture_runtime_version': self.runtime_version}, 'tasks': prepare + selected + verify}]
        file = self.path / 'play.yml'
        file.write_text(yaml.safe_dump(play, sort_keys=False))
        before = self.log.read_text().splitlines() if self.log.exists() else []
        result = run(['ansible-playbook', '-i', 'localhost,', str(file), *(['--check'] if check else [])], env=self.env)
        output = self.path / 'last-run.log'
        output.write_text(result.stdout + result.stderr)
        if failure:
            assert result.returncode != 0, 'Expected the invalid Dockerfile to fail'
        elif result.returncode:
            raise AssertionError(f'{self.role} failed; see {output}\n{result.stdout}\n{result.stderr}')
        calls = [json.loads(x) for x in self.log.read_text().splitlines()[len(before):]]
        applies = [x for x in calls if 'compose' in x and 'up' in x and '--dry-run' not in x]
        assert len(applies) == (0 if check else 1), (self.role, applies)
        if check:
            assert not any('build' in x and 'compose' in x for x in calls), calls
        return applies[0] if applies else []

    def cleanup(self):
        # Only resources belonging to this UUID-named fixture are removed.
        file = self.path / 'compose.yaml'
        if file.exists():
            require([self.docker, 'compose', '-p', self.name, '-f', str(file), 'down', '--remove-orphans', '--volumes'], env=self.env)
        for image in set(self.images):
            run([self.docker, 'image', 'rm', image], env=self.env)


def exercise(root, role, docker, env, base):
    f = Fixture(root, role, docker, env, base)
    try:
        if role == 'musicbrainz':
            f.extra_build = True
        first = f.execute()
        state = f.state()
        if role == 'stash':
            config = f.path / 'config/config.yml'
            assert yaml.safe_load(config.read_text())['dangerous_allow_public_without_auth'] is True
            config.write_text(yaml.safe_dump({'username': 'fixture', 'password': 'fixture',
                'security_tripwire_accessed_from_public_internet': True, 'custom_setting': 'preserve'}))
            f.execute()
            result = yaml.safe_load(config.read_text())
            assert result == {'dangerous_allow_public_without_auth': True, 'custom_setting': 'preserve'}, result
            state = f.state()
        if f.is_build:
            assert '--build' in first, first
        second = f.execute()
        assert f.state() == state, (role, 'unchanged deployment recreated a container')
        if f.is_build:
            assert '--no-build' in second, second
        f.config_version = 'two'
        changed = f.execute()
        newer = f.state()
        assert newer['app'] != state['app'], role
        assert newer['companion'] == state['companion'], role
        if f.is_build:
            assert '--no-build' in changed, changed
        if f.flags:
            f.runtime_version = 'two'
            changed = f.execute()
            state = f.state()
            assert all(state[k] != newer[k] for k in state), (role, 'runtime change did not recreate the stack')
            if f.is_build:
                assert '--no-build' in changed, changed
        if f.is_build:
            marker = f.path / '.ansible-build-inputs.json'
            old = marker.read_bytes()
            f.dockerfile.write_text(f'FROM {base}\nINVALID_INSTRUCTION fail\n')
            assert '--build' in f.execute(failure=True)
            assert '--build' in f.execute(failure=True)
            assert marker.read_bytes() == old
            # A persistent source input change must still trigger the retry.
            f.dockerfile.write_text(f'FROM {base}\nLABEL fixture.version="two"\n')
            assert '--build' in f.execute()
            assert marker.read_bytes() != old
            assert '--no-build' in f.execute()
            f.buildarg_version = 'two'
            assert '--build' in f.execute()
            assert '--no-build' in f.execute()
            f.vars[f'{role}_force_rebuild'] = True
            assert '--build' in f.execute()
            f.vars[f'{role}_force_rebuild'] = False
            # Remove only the fixture containers/image to simulate local image loss.
            require([docker, 'compose', '-p', f.name, '-f', str(f.path / 'compose.yaml'), 'down'], env=f.env)
            require([docker, 'image', 'rm', f.images[0]], env=f.env)
            assert '--build' in f.execute()
            source = {'line': 'line_git', 'petlibro': 'catbro_git', 'musicbrainz': 'musicbrainz_git'}.get(role)
            if source:
                f.vars[source] = {'after': 'revision-2'}
                assert '--build' in f.execute()
                assert '--no-build' in f.execute()
            marker_before = marker.read_bytes()
            state = f.state()
            f.dockerfile.write_text(f'FROM {base}\nLABEL fixture.version="check"\n')
            f.execute(check=True)
            assert f.state() == state and marker.read_bytes() == marker_before
        if role == 'petlibro':
            f.enabled = False
            assert '--no-build' in f.execute()
            assert 'app' not in f.state()
            assert '--no-build' in f.execute()
        print(f'PASS: {role} lifecycle', flush=True)
    finally:
        f.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roles', nargs='+', default=['prowlarr', 'aurral', 'stash', *BUILD_ROLES])
    parser.add_argument('--base-image', default='alpine:3.20')
    parser.add_argument('--static-only', action='store_true')
    args = parser.parse_args()
    static_checks()
    if args.static_only:
        return
    docker = shutil.which('docker')
    context_endpoint = require([docker, 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'])
    endpoint = context_endpoint if os.environ.get('DOCKER_CONTEXT') else os.environ.get('DOCKER_HOST', context_endpoint)
    if not endpoint.startswith('unix://'):
        raise SystemExit('Tests require a local Docker Unix socket; remote daemons are not supported.')
    root = Path(tempfile.mkdtemp(prefix='homelab-compose-tests-'))
    print(f'Fixture logs: {root}', flush=True)
    config = root / 'ansible.cfg'
    config.write_text('[defaults]\nretry_files_enabled = False\nhost_key_checking = False\n')
    docker_config = root / 'docker-config'
    docker_config.mkdir()
    (docker_config / 'config.json').write_text(json.dumps({'cliPluginsExtraDirs': [str(Path.home() / '.docker/cli-plugins')]}))
    env = dict(os.environ, DOCKER_CONFIG=str(docker_config), ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(root / 'ansible-tmp'),
               DOCKER_HOST=endpoint, ANSIBLE_REMOTE_TEMP=str(root / 'remote-tmp'), ANSIBLE_NOCOLOR='1')
    env.pop('DOCKER_CONTEXT', None)
    if run([docker, 'image', 'inspect', args.base_image], env=env).returncode:
        require([docker, 'pull', args.base_image], env=env)
    decision_checks(root, env)
    template_checks(root, env, docker)
    for role in args.roles:
        exercise(root, role, docker, env, args.base_image)
    print('PASS: all requested lifecycle scenarios; fixture containers and images removed', flush=True)


if __name__ == '__main__':
    main()
