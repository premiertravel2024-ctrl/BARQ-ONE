"""Regression for v2.31 Inno smoke exit 5 after successful EXE compilation.

Static pipeline checks run on Linux. The Windows installer must still be
executed and verified on a real Windows host; these tests do not simulate it.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_keeps_real_install_validation_and_fail_closed_contract():
    script = (ROOT / 'scripts/smoke_install.ps1').read_text(encoding='utf-8')
    for required in (
        '/BARQSMOKE=1', '/SMOKEID=', '/DIR=', '/LOG=', '/NOCLOSEAPPLICATIONS',
        'if ($exitCode -ne 0)', 'installed-self-test.json',
        'BARQ_Wake.exe', 'BARQ.exe', '--self-test',
        "if ($data.status -ne 'ok'", 'throw',
    ):
        assert required in script, required
    assert "Join-Path $local 'Bq\\smoke'" in script
    assert "[Guid]::NewGuid().ToString('N')" in script
    assert 'installer-smoke-diagnostics.txt' in script
    assert 'Get-InstallLogTail' in script
    assert 'Select-Object -Last 130' in script
    assert '$success = $true' in script
    assert 'finally {' in script and 'unins000.exe' in script


def test_staged_builder_copies_failed_installer_diagnostics_to_original_source():
    src = (ROOT / 'scripts/build_short_path.py').read_text(encoding='utf-8')
    assert "log.name.startswith('installer-smoke')" in src
    assert "diagnostic.name.startswith('installer-smoke')" in src
    build = (ROOT / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert 'smoke_install.ps1' in build
    assert 'BARQ_Setup_' in build
    assert build.index('Smoke-testing the actual packaged Windows executable') < build.index("smoke_install.ps1")
    assert 'Set-Content -LiteralPath $buildMarker' in build[build.index('smoke_install.ps1'):]


def test_recheck_existing_compiled_setup_is_real_smoke_not_a_bypass():
    ps = (ROOT / 'scripts/run_existing_installer_smoke.ps1').read_text(encoding='utf-8')
    bat = (ROOT / 'RUN_EXISTING_SETUP_SMOKE.bat').read_text(encoding='utf-8')
    assert 'Sort-Object LastWriteTime -Descending' in ps
    assert "'smoke_install.ps1'" in ps
    assert '-Setup $Setup -Version $version -ReportDir $release' in ps
    assert 'installer-smoke-diagnostics.txt' in bat
    assert 'if errorlevel 1' in bat
