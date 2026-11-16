"""Prevent ZIP release packaging from silently omitting BARQ's build package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from package_full_source import ROOT, EXPLICIT_CRITICAL_FILES, should_include
from scripts.verify_source_integrity import verify


def test_zip_packaging_includes_critical_build_package():
    for name in EXPLICIT_CRITICAL_FILES:
        assert should_include(Path(name)), f'{name} must never be excluded'
        assert (ROOT / name).is_file(), f'{name} missing from source'


def test_zip_packaging_excludes_caches_and_secrets_only():
    assert not should_include(Path('frontend/node_modules/package/index.js'))
    assert not should_include(Path('build/__pycache__/jobs.cpython-311.pyc'))
    assert not should_include(Path('.env'))
    assert not should_include(Path('config/.env.local'))
    assert should_include(Path('build/jobs.py'))
    assert should_include(Path('build/__init__.py'))
    assert should_include(Path('verification/v2.29/tests.log'))
    assert not should_include(Path('private-runtime.log'))


def test_source_integrity_preflight_still_enabled():
    assert not verify(ROOT)
