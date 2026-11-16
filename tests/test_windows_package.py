"""Build pipeline contracts; frozen binary is exercised on a Windows CI runner."""
import json
from pathlib import Path
import desktop

ROOT=Path(__file__).resolve().parents[1]


def test_selftest_writes_a_machine_readable_report(tmp_path,monkeypatch):
    monkeypatch.setattr(desktop,'bundled_health_check',lambda:{'status':'ok','frozen':True,'ui':'react'})
    dest=tmp_path/'output'/'result.json'
    assert desktop.write_self_test_report(str(dest)) == 0
    assert json.loads(dest.read_text(encoding='utf-8'))['ui'] == 'react'


def test_selftest_reports_error_without_claiming_success(tmp_path,monkeypatch):
    def broken():
        raise RuntimeError('Missing packaged resources')
    monkeypatch.setattr(desktop,'bundled_health_check',broken)
    report=tmp_path/'result.json'
    assert desktop.write_self_test_report(str(report)) == 1
    assert json.loads(report.read_text(encoding='utf-8'))['status'] == 'error'


def test_build_does_not_skip_frontend_tests_or_frozen_executable():
    script=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    # pytest is launched through the bounded, logged Python gate now; requiring
    # the literal old 'pytest -q' would falsely reject a secure Windows build.
    # The import preflight intentionally runs BEFORE npm. Do not mistake that
    # early --check-imports call for the full, mandatory pytest gate: the
    # actual gate executes as a Python module AFTER the frontend build.
    import re

    def command_position(pattern: str) -> int:
        match = re.search(pattern, script, flags=re.MULTILINE)
        assert match is not None, f"Required build command missing: {pattern}"
        return match.start()

    preflight = command_position(
        r"^& py -3\.11 \(Join-Path \$PSScriptRoot 'run_python_build_tests\.py'\) --check-imports\s*$"
    )
    frontend = command_position(r"^\s*Invoke-Step '[^']+' \{ npm run build \}\s*$")
    pytest_gate = command_position(r"^& \$python -m scripts\.run_python_build_tests\s*$")
    pyinstaller = command_position(r"^\s*'-m', 'PyInstaller',")
    frozen_selftest = command_position(r"^\$smokeProcess = Start-Process -FilePath \$exe -ArgumentList @\('--self-test',")
    inno = command_position(r"^\$installerScript = Join-Path \$root 'scripts\\installer\.iss'\s*$")
    assert preflight < frontend < pytest_gate < pyinstaller < frozen_selftest < inno
    # The full gate MUST fail closed; the earlier import check alone is not a
    # substitute for pytest. Validate the adjacent exit-code guard explicitly.
    assert re.search(
        r"^& \$python -m scripts\.run_python_build_tests\s*\n"
        r"if \(\$LASTEXITCODE -ne 0\) \{",
        script, flags=re.MULTILINE,
    )
    assert 'self-test.json' in script
    for step in ('npm run test:ui', 'npm run test:imports', 'npm run test:frontend'):
        assert step in script
    runner = (ROOT/'scripts/run_python_build_tests.py').read_text(encoding='utf-8')
    assert "'-m', 'pytest'" in runner
    assert "'--maxfail=20'" in runner
    assert 'if ($LASTEXITCODE -ne 0)' in script
    assert 'web/react/index.html' in script
    assert '--windowed' in script


def test_windows_builder_assets_and_no_bundled_keys():
    assert (ROOT/'assets/app.ico').stat().st_size > 1000
    from core.version import VERSION
    assert f'AppVersion "{VERSION}"' in (ROOT/'scripts/installer.iss').read_text(encoding='utf-8')
    assert 'BUILD_WINDOWS_EXE.bat' in [x.name for x in ROOT.iterdir()]
    ignore=(ROOT/'.gitignore').read_text(encoding='utf-8')
    assert '.env' in ignore and '*.sqlite' in ignore
    assert f'BARQ_Setup_{VERSION}.exe' in (ROOT/'.github/workflows/windows-build.yml').read_text(encoding='utf-8')


def test_frozen_gui_selftest_waits_for_process_and_reports_errors():
    script=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    # Windows PowerShell does not necessarily await GUI programs invoked with '&'.
    # The self-test report must only be inspected after Start-Process -Wait.
    assert 'Start-Process -FilePath $exe' in script
    assert '-Wait -PassThru' in script
    assert 'self-test.stderr.log' in script
    assert 'smokeProcess.ExitCode' in script
    assert script.index('Start-Process -FilePath $exe') < script.index("if (-not (Test-Path -LiteralPath $report -PathType Leaf))")
    assert 'Bundled .exe self-test did not create a report.' not in script


def test_autopilot_guard_runs_before_frontend_checks():
    """The source permission policy must be tested before slow build steps."""
    script = (ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    install = script.index('npm ci --no-audit --no-fund --include=dev')
    guard = script.index("Invoke-Step 'Testing scoped autopilot permission guard'")
    typecheck = script.index("Invoke-Step 'Type-checking the complete frontend'")
    assert install < guard < typecheck
    assert script.count("Invoke-Step 'Testing scoped autopilot permission guard'") == 1
    source = (ROOT/'frontend/src/lib/approvals.ts').read_text(encoding='utf-8')
    assert "if(tool==='workspace_edit')return isManaged(path);" in source
    assert "tool==='code_replace')return isManaged(path);" not in source
