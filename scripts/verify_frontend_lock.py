"""Offline npm lock verification, before any downloads or release staging.

Checks the actual package URLs and hashes, and pins a verified registry-metadata
contract for a previously broken resolve/is-core-module pair. Does not modify
package versions or bypass npm ci integrity checks. Only the standard library
is required so this gate can run before npm/Python dependencies are installed.
"""
from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

# Metadata confirmed against published npm package-lock entries and the
# upstream browserify/resolve v1.22.13 package.json. Previously the lockfile
# claimed is-core-module@2.18.2 but kept the 2.17.0 tarball's exact integrity.
# A package URL/semver edit without the correct hash is never acceptable.
_VETTED = {
    'is-core-module': {
        'version': '2.17.0',
        'integrity': 'sha512-J/vG0zBCbIKOQFfufSwyXdMrsohyJIUNkrnmo6WZGzoM7tr/lsbfW5b2BvisL6zsyMzK9UxV9L6c7AoFbyXHOA==',
    },
    'resolve': {
        'version': '1.22.13',
        'integrity': 'sha512-Dj/cW9zBV2aRj6XzCxuGIs3ESZKv02jixne3q6jFZYZ3/Tg09gHHviSMDL4kObh9pqSahdRHEnDoaP2gn8YLhA==',
    },
}


def verify(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads((root / 'frontend' / 'package.json').read_text(encoding='utf-8'))
        lock = json.loads((root / 'frontend' / 'package-lock.json').read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        return [f'Cannot read frontend package manifest/lock: {exc}']
    packages = lock.get('packages')
    if lock.get('lockfileVersion') != 3 or not isinstance(packages, dict):
        return ['Expected npm package-lock v3 with a packages index; do not generate a lock by hand.']
    root_package = packages.get('')
    if not isinstance(root_package, dict):
        return ['Missing package-lock root package.']
    for field in ('name', 'version'):
        if root_package.get(field) != manifest.get(field):
            errors.append(f'package-lock root {field} differs from package.json.')
    for group in ('dependencies', 'devDependencies'):
        if root_package.get(group, {}) != manifest.get(group, {}):
            errors.append(f'package-lock root {group} differs from package.json.')
    for path, record in packages.items():
        if not path:
            continue
        if not isinstance(record, dict):
            errors.append(f'Invalid package record: {path}')
            continue
        if 'resolved' not in record:
            # Bundled/link package records do not need a tarball.
            continue
        name = path.rsplit('node_modules/', 1)[-1]
        version = str(record.get('version', ''))
        resolved = str(record['resolved'])
        address = urlsplit(resolved)
        tarname = unquote(address.path.rsplit('/', 1)[-1])
        expected_tarname = f'{name.rsplit("/", 1)[-1]}-{version}.tgz'
        if (address.scheme != 'https' or address.netloc != 'registry.npmjs.org'
                or tarname != expected_tarname or address.query or address.fragment):
            errors.append(f'{path}: registry tarball URL does not match the locked package/version.')
        integrity = str(record.get('integrity', ''))
        if not integrity.startswith('sha512-'):
            errors.append(f'{path}: missing sha512 integrity value.')
        else:
            try:
                digest = base64.b64decode(integrity[7:], validate=True)
                if len(digest) != 64:
                    errors.append(f'{path}: incorrect sha512 digest length.')
            except (ValueError, binascii.Error):
                errors.append(f'{path}: invalid sha512 base64 digest.')
    for name, contract in _VETTED.items():
        record = packages.get(f'node_modules/{name}', {})
        if (record.get('version'), record.get('integrity')) != (contract['version'], contract['integrity']):
            errors.append(
                f'{name} lock version/integrity disagrees with the vetted published package: '
                f"expected {contract['version']} and its matching sha512."
            )
    resolve_deps = packages.get('node_modules/resolve', {}).get('dependencies', {})
    if resolve_deps.get('is-core-module') != '^2.17.0':
        errors.append('resolve@1.22.13 published dependency is is-core-module ^2.17.0, not ^2.18.2.')
    return errors


if __name__ == '__main__':
    problems = verify()
    if problems:
        for problem in problems:
            print('[BARQ NPM LOCK] FAIL: ' + problem, file=sys.stderr)
        raise SystemExit(1)
    print('[BARQ NPM LOCK] PASS: locked npm URLs/digests and vetted resolve/is-core-module metadata consistent.')
