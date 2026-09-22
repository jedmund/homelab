#!/usr/bin/env python3
"""Stopped-data transfer checks for the max -> nuc-mini migration.

No network access, application control, or reverse-copy behavior. Ansible owns
stopping containers, transfer, permissions, routing, and checkpoint completion.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

IDENTITY = 'degoog-max-to-nuc-mini-v1'


def digest(path):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def checkpoint(root):
    path = root / '.degoog-migration.json'
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if value.get('migration') != IDENTITY or value.get('state') not in ('prepared', 'restored', 'complete'):
        raise ValueError('Unrecognized migration checkpoint')
    return value


def write_checkpoint(root, state, checksum):
    path = root / '.degoog-migration.json'
    fd, temp = tempfile.mkstemp(prefix='.migration-marker-', dir=root)
    try:
        with os.fdopen(fd, 'w') as target:
            json.dump(dict(migration=IDENTITY, state=state, sha256=checksum), target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate_data(data):
    if not data.is_dir() or data.is_symlink():
        raise ValueError('Data directory missing or a symlink')
    for path in data.rglob('*'):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError('Unsupported link or special file in data')
        if not path.is_file():
            continue
        with path.open('rb') as source:
            header = source.read(16)
        if header == b'SQLite format 3\x00':
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('SQLite integrity check failed')


def preflight(root):
    if root.is_symlink():
        raise ValueError('Destination root must not be a symlink')
    current = checkpoint(root)
    data = root / 'data'
    if current is None and data.exists():
        raise ValueError('Destination data already exists without a migration checkpoint')
    if current and current['state'] in ('restored', 'complete') and not data.is_dir():
        raise ValueError('Checkpoint exists but restored data is missing')
    return current


def archive(root, target):
    validate_data(root / 'data')
    fd, temp = tempfile.mkstemp(prefix='.archive-', dir=target.parent)
    os.close(fd)
    try:
        with tarfile.open(temp, 'w:gz') as bundle:
            bundle.add(root / 'data', arcname='data', recursive=True)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def restore(root, source, checksum):
    current = preflight(root)
    if current and current['state'] in ('restored', 'complete'):
        return False  # Never replace a running destination with old source data.
    if digest(source) != checksum:
        raise ValueError('Archive checksum mismatch')
    if current and current['sha256'] != checksum:
        raise ValueError('Prepared checkpoint belongs to a different archive')
    stage = Path(tempfile.mkdtemp(prefix='.degoog-transfer-', dir=root))
    try:
        with tarfile.open(source, 'r:gz') as bundle:
            for member in bundle.getmembers():
                parts = Path(member.name).parts
                if not parts or parts[0] != 'data' or '..' in parts or not (member.isfile() or member.isdir()):
                    raise ValueError('Unsafe archive member')
            bundle.extractall(stage, filter='data')
        validate_data(stage / 'data')
        write_checkpoint(root, 'prepared', checksum)
        if (root / 'data').exists():
            # Resume a crash between the atomic directory move and marker write.
            expected = {str(p.relative_to(stage / 'data')): digest(p)
                        for p in (stage / 'data').rglob('*') if p.is_file()}
            validate_data(root / 'data')
            actual = {str(p.relative_to(root / 'data')): digest(p)
                      for p in (root / 'data').rglob('*') if p.is_file()}
            if actual != expected:
                raise ValueError('Destination differs from the prepared archive; refusing overwrite')
        else:
            os.replace(stage / 'data', root / 'data')
        write_checkpoint(root, 'restored', checksum)
        return True
    finally:
        shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'archive', 'restore', 'complete'])
    parser.add_argument('root', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.action == 'preflight':
        state = preflight(args.root)
        print(state['state'] if state else 'new')
    elif args.action == 'archive':
        archive(args.root, args.archive)
        print(digest(args.archive))
    elif args.action == 'restore':
        print('restored' if restore(args.root, args.archive, args.sha256) else 'unchanged')
    else:
        current = checkpoint(args.root)
        if not current or current['state'] not in ('restored', 'complete'):
            raise ValueError('No restored checkpoint to complete')
        if current['state'] != 'complete':
            write_checkpoint(args.root, 'complete', current['sha256'])
        print('complete')


if __name__ == '__main__':
    main()
