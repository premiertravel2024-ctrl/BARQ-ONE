"""Build and verify a complete BARQ source ZIP with SHA-256 manifest.

Run from any directory:
    py -3.11 scripts/package_full_source.py --output BARQ_FULL_SOURCE.zip

The source package `build/jobs.py` is intentional source code, NOT a generated
build folder. Never ignore directories just because their name is `build`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git', 'node_modules', '.venv', 'venv', '.buildvenv',
                 '__pycache__', '.pytest_cache', '.mypy_cache', 'dist',
                 'release', '.build-state', '.next', '.turbo', 'coverage'}
EXCLUDED_FILES = {'.env', '.DS_Store', 'Thumbs.db', 'SOURCE_MANIFEST_SHA256.json'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.log', '.sqlite', '.sqlite3', '.db', '.whl'}
PREFIX = 'BARQ/'
MANIFEST = 'SOURCE_MANIFEST_SHA256.json'
EXPLICIT_CRITICAL_FILES = (
    'build/__init__.py', 'build/jobs.py',
    'scripts/build_windows.ps1', 'scripts/verify_source_integrity.py',
    'frontend/src/App.tsx', 'frontend/package-lock.json',
    '.github/workflows/windows-build.yml',
)


def should_include(relative: Path) -> bool:
    """Check archive candidates without confusing `build/` source with outputs."""
    path = Path(relative)
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return False
    if path.name in EXCLUDED_FILES:
        return False
    if path.name.startswith('.env.') and path.name != '.env.example':
        return False
    if path.suffix.lower() == '.log':
        return bool(path.parts and path.parts[0] == 'verification')
    return path.suffix.lower() not in EXCLUDED_SUFFIXES

PREFLIGHTS = (
    'scripts/verify_source_integrity.py',
    'scripts/verify_release_consistency.py',
    'scripts/verify_ci_dependencies.py',
    'scripts/audit_release_readiness.py',
)


def eligible_files(root: Path):
    """Preserve Python `build/` package; omit generated/secret artifacts only."""
    for directory, subdirs, names in os.walk(root, topdown=True, followlinks=False):
        here = Path(directory)
        subdirs[:] = sorted(d for d in subdirs if should_include((here / d).relative_to(root))
                            and not (here / d).is_symlink())
        for name in sorted(names):
            path = here / name
            if path.is_symlink() or not path.is_file():
                continue
            if not should_include(path.relative_to(root)):
                continue
            yield path.relative_to(root).as_posix(), path


def manifest_bytes(files: dict[str, bytes]):
    version = '2.31.0'
    installer = files.get('scripts/installer.iss', b'')
    import re
    match = re.search(rb'^#define AppVersion "([\d.]+)"', installer, re.MULTILINE)
    if match:
        version = match.group(1).decode('ascii')
    obj = {'version': version,
           'files': {key: hashlib.sha256(data).hexdigest()
                     for key, data in sorted(files.items())}}
    return (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def verify_archive(archive: Path, *, preflights: bool = True) -> dict:
    """Fail closed on missing source, stale manifest, byte mismatches, unsafe paths."""
    archive = Path(archive)
    with ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f'ZIP checksum failure: {bad}')
        listed = z.namelist()
        if len(listed) != len(set(listed)):
            raise ValueError('Duplicate ZIP entries')
        if not listed or any(not name.startswith(PREFIX) for name in listed):
            raise ValueError('ZIP must have one BARQ/ root')
        for name in listed:
            path = Path(name)
            if '..' in path.parts or name.startswith('/') or '\\' in name:
                raise ValueError(f'Unsafe archive entry: {name}')
            if ((z.getinfo(name).external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError(f'Symlink not permitted: {name}')
        rel_paths = {name.removeprefix(PREFIX) for name in listed if not name.endswith('/')}
        if MANIFEST not in rel_paths:
            raise ValueError('Archive is missing a SHA-256 source manifest')
        manifest = json.loads(z.read(PREFIX + MANIFEST))
        expected = manifest.get('files', {})
        if not isinstance(expected, dict) or not expected:
            raise ValueError('Archive manifest has no file map')
        if set(expected) != (rel_paths - {MANIFEST}):
            missing = sorted(set(expected) - rel_paths)
            unexpected = sorted((rel_paths - {MANIFEST}) - set(expected))
            raise ValueError(f'Incomplete archive: missing={missing[:12]}, unexpected={unexpected[:12]}')
        for rel, wanted in expected.items():
            content = z.read(PREFIX + rel)
            if hashlib.sha256(content).hexdigest() != wanted:
                raise ValueError(f'Content hash mismatch in archive: {rel}')
        for required in EXPLICIT_CRITICAL_FILES:
            if required not in rel_paths:
                raise ValueError(f'Critical source module missing: {required}')
        if preflights:
            with tempfile.TemporaryDirectory(prefix='barq-zip-verify-') as t:
                # Unpack a *real* copy of the archive, then run actual release gates.
                z.extractall(t)
                extracted_root = Path(t) / 'BARQ'
                for script in PREFLIGHTS:
                    result = subprocess.run([sys.executable, str(extracted_root / script)],
                                            cwd=extracted_root, capture_output=True,
                                            text=True, timeout=90)
                    if result.returncode:
                        raise ValueError(f'Extracted release preflight failed: {script}\n'
                                         + (result.stdout + result.stderr)[-3500:])
        return {'files': len(expected), 'version': manifest.get('version'),
                'required_build_module': 'build/jobs.py', 'preflights': 'passed' if preflights else 'not run'}


def package_source(root: Path, output: Path):
    root = root.resolve()
    output = output.resolve()
    if root in output.parents:
        raise ValueError('Output ZIP must be outside the source tree')
    payload = {rel: path.read_bytes() for rel, path in eligible_files(root)}
    for rel in ('build/jobs.py', 'build/__init__.py'):
        if rel not in payload:
            raise ValueError(f'Required Python source package missing: {rel}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.partial.zip')
    try:
        with ZipFile(temporary, 'w', compression=ZIP_DEFLATED, compresslevel=6) as z:
            for rel, data in sorted(payload.items()):
                z.writestr(PREFIX + rel, data)
            z.writestr(PREFIX + MANIFEST, manifest_bytes(payload))
        result = verify_archive(temporary, preflights=True)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=False, help='Build full source ZIP to this path')
    ap.add_argument('--verify', help='Check an existing archive and extracted source preflight')
    args = ap.parse_args()
    if not (args.output or args.verify):
        ap.error('Use --output or --verify')
    try:
        if args.output:
            result = package_source(ROOT, Path(args.output))
            print('BARQ COMPLETE SOURCE ZIP PASS:', json.dumps(result))
        if args.verify:
            result = verify_archive(Path(args.verify))
            print('BARQ ARCHIVE VERIFIED:', json.dumps(result))
    except (ValueError, OSError, BadZipFile, subprocess.TimeoutExpired) as exc:
        print(f'BARQ SOURCE PACKAGE FAILED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
