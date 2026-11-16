"""Regression tests: complete release ZIP must retain the BARQ Python build package."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import pytest

from scripts.package_full_source import eligible_files, manifest_bytes, verify_archive


def make_zip(path: Path, contents: dict[str, bytes]):
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr('BARQ/' + name, content)
        archive.writestr('BARQ/SOURCE_MANIFEST_SHA256.json', manifest_bytes(contents))


def test_python_build_package_is_not_treated_as_generated_build_output(tmp_path):
    (tmp_path / 'build').mkdir()
    (tmp_path / 'build/jobs.py').write_text('JOBS={}\n')
    (tmp_path / 'build/__init__.py').write_text('')
    (tmp_path / 'build/__pycache__').mkdir()
    (tmp_path / 'build/__pycache__/jobs.pyc').write_bytes(b'cache')
    (tmp_path / 'release').mkdir()
    (tmp_path / 'release/old.exe').write_bytes(b'old output')
    files = dict(eligible_files(tmp_path))
    assert 'build/jobs.py' in files
    assert 'build/__init__.py' in files
    assert 'build/__pycache__/jobs.pyc' not in files
    assert 'release/old.exe' not in files


def test_archive_rejects_missing_build_jobs_even_with_self_consistent_manifest(tmp_path):
    path = tmp_path / 'missing.zip'
    make_zip(path, {'build/__init__.py': b'', 'scripts/build_windows.ps1': b''})
    with pytest.raises(ValueError, match='Critical source module missing'):
        verify_archive(path, preflights=False)


def test_archive_rejects_checksum_mismatch(tmp_path):
    path = tmp_path / 'mismatch.zip'
    content = {'build/__init__.py': b'', 'build/jobs.py': b'# good',
               'scripts/build_windows.ps1': b'', 'scripts/verify_source_integrity.py': b'',
               'frontend/src/App.tsx': b'', 'frontend/package-lock.json': b'',
               '.github/workflows/windows-build.yml': b''}
    make_zip(path, content)
    with ZipFile(path) as z:
        old_manifest = z.read('BARQ/SOURCE_MANIFEST_SHA256.json')
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for name, data in content.items():
            z.writestr('BARQ/' + name, b'# changed' if name == 'build/jobs.py' else data)
        z.writestr('BARQ/SOURCE_MANIFEST_SHA256.json', old_manifest)
    with pytest.raises(ValueError, match='Content hash mismatch'):
        verify_archive(path, preflights=False)


def test_archive_rejects_unmanifested_extra_file(tmp_path):
    path = tmp_path / 'extra.zip'
    content = {'build/jobs.py': b''}
    make_zip(path, content)
    with ZipFile(path, 'a') as z:
        z.writestr('BARQ/added.py', b'new')
    with pytest.raises(ValueError, match='Incomplete archive'):
        verify_archive(path, preflights=False)
