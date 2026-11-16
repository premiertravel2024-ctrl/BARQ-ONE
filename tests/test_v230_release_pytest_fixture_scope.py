"""Regression: release-gate generated fixtures may not be under AppData.

We retain coverage for explicit, approved Temp roots in the device-index tests;
this only controls *pytest's* own temporary directory for the release pipeline.
"""
from pathlib import Path
import shutil

from computer_control.safety.policy import sensitive
from scripts.run_python_build_tests import create_safe_pytest_basetemp
from services.device_index import _safe_path


def test_generated_pytest_workspace_is_safe_and_unique(tmp_path):
    a = create_safe_pytest_basetemp(tmp_path)
    b = create_safe_pytest_basetemp(tmp_path)
    try:
        assert a != b and a.parent == b.parent == tmp_path
        assert not sensitive(str(a))
        assert _safe_path(a, explicit_root=a)
        assert a.is_dir() and b.is_dir()
    finally:
        shutil.rmtree(a)
        shutil.rmtree(b)


def test_release_gate_runs_original_suite_with_explicit_safe_basetemp():
    code = (Path(__file__).resolve().parents[1] / 'scripts/run_python_build_tests.py').read_text(encoding='utf-8')
    assert "f'--basetemp={pytest_basetemp}'" in code
    assert "'--maxfail=20'" in code
    assert "'--timeout=90'" in code
    assert 'pytest_fixture_root=' in code
    assert 'shutil.rmtree(pytest_basetemp' in code


def test_refuses_appdata_outside_consent_scope(tmp_path):
    blocked = tmp_path / 'AppData' / 'Roaming' / 'secrets'
    blocked.mkdir(parents=True)
    try:
        create_safe_pytest_basetemp(blocked)
    except ValueError as exc:
        assert 'Unsafe Windows pytest fixture root' in str(exc)
    else:
        raise AssertionError('Release pytest gate must refuse unsafe fixture roots')
