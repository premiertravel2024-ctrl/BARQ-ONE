"""Regression checks for Windows PowerShell quoted Python -c failure."""
import ast
from pathlib import Path
from scripts.verify_python_build import validate

ROOT = Path(__file__).resolve().parents[1]


def test_probe_file_has_valid_python_syntax():
    ast.parse((ROOT/'scripts/verify_python_build.py').read_text(encoding='utf-8'))


def test_python_probe_passes_good_version():
    assert validate((3,11),64)[0]


def test_python_probe_rejects_incompatible_version():
    assert not validate((3,12),64)[0]
    assert not validate((3,11),32)[0]


def test_powershell_does_not_inline_python_code_through_c_flag():
    code=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert '& py -3.11 $pythonCheck' in code
    assert "Join-Path $PSScriptRoot 'verify_python_build.py'" in code
    assert "-3.11 -c" not in code
    assert 'if ($LASTEXITCODE -ne 0)' in code


def test_launcher_keeps_single_flat_layout_and_honors_build_result():
    assert (ROOT/'BUILD_BARQ.bat').exists()
    assert (ROOT/'scripts/build_windows.ps1').exists()
    assert not (ROOT/'BARQ_Source').exists()
    for filename in ('BUILD_BARQ.bat','BUILD_WINDOWS_EXE.bat'):
        content=(ROOT/filename).read_text(encoding='utf-8')
        assert 'if errorlevel 1' in content
