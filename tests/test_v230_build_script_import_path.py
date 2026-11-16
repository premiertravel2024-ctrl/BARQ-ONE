"""Release gate must import BARQ services even when launched from outside the repo."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_python_build_tests.py"


def test_direct_script_imports_services_outside_project_root(tmp_path):
    """Replicate Windows: launch scripts/run_python_build_tests.py by absolute path.

    The -I flag deliberately disables PYTHONPATH and the implicit current-directory
    search path. This test used to fail with 'No module named services'.
    """
    probe = r"""
import pathlib, runpy, shutil, sys
script = pathlib.Path(sys.argv[1])
parent = pathlib.Path(sys.argv[2])
ns = runpy.run_path(str(script))
created = ns['create_safe_pytest_basetemp'](parent)
try:
    assert created.is_dir()
    assert created.parent == parent
    from services import device_index
    assert pathlib.Path(device_index.__file__).resolve() == script.parent.parent / 'services' / 'device_index.py'
    print('[BARQ PYTEST IMPORT] PASS')
finally:
    shutil.rmtree(created)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(RUNNER), str(tmp_path)],
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[BARQ PYTEST IMPORT] PASS" in result.stdout


def test_import_preflight_works_directly_from_outside_repository(tmp_path):
    result = subprocess.run(
        [sys.executable, "-I", str(RUNNER), "--check-imports"],
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True, text=True, timeout=25, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[BARQ PYTEST IMPORT] PASS" in result.stdout


def test_windows_build_checks_imports_early_and_uses_module_mode():
    content = (ROOT / 'scripts' / 'build_windows.ps1').read_text(encoding='utf-8')
    assert "run_python_build_tests.py') --check-imports" in content
    assert content.index("--check-imports") < content.index('npm ci')
    assert '& $python -m scripts.run_python_build_tests' in content
