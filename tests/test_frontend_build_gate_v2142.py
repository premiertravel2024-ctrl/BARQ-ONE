"""Regression: a release can't silently skip the React compiler or install stale UI."""
from pathlib import Path
import json
from scripts.verify_ci_dependencies import workflow_job_dependencies, verify as verify_workflow

ROOT = Path(__file__).resolve().parents[1]
from core.version import VERSION as VER
TOKEN = f'v{VER}-build-gated-ui'


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8-sig')


def test_preview_icon_supported_in_locked_lucide_version():
    tsx = read('frontend/src/components/workspace/PreviewPanel.tsx')
    assert 'TabletSmart' not in tsx
    assert 'Tablet' in tsx


def test_frontend_real_export_guard_is_part_of_build_and_has_its_own_tests():
    pkg = json.loads(read('frontend/package.json'))
    assert pkg['version'] == VER
    assert 'verify:icons' in pkg['scripts']['build']
    assert 'tsc --noEmit' in pkg['scripts']['build']
    assert 'vite build' in pkg['scripts']['build']
    assert 'check-lucide-imports.mjs' in pkg['scripts']['verify:icons']
    assert (ROOT / 'frontend/scripts/check-lucide-imports.test.mjs').is_file()


def test_windows_release_never_skips_real_react_and_binary_checks():
    ps = read('scripts/build_windows.ps1')
    assert f"$version = '{VER}'" in ps
    assert TOKEN in ps
    assert 'npm ci --no-audit --no-fund' in ps
    assert 'npm run test:imports' in ps
    assert 'npm run build' in ps
    assert "Running project unit and API tests" in ps
    assert "Smoke-testing the actual packaged Windows executable" in ps
    assert "Building Windows Setup.exe" in ps
    assert ps.index('npm run build') < ps.index('Running project unit and API tests')
    assert ps.index('Running project unit and API tests') < ps.index('Smoke-testing the actual packaged Windows executable')
    assert ps.index('Smoke-testing the actual packaged Windows executable') < ps.index('Building Windows Setup.exe')
    assert TOKEN in read('frontend/src/components/workspace/WorkspaceStudio.tsx')


def test_ci_dependency_parser_accepts_supported_yaml_styles():
    for dependency in ('needs: frontend-validation',
                       'needs: [frontend-validation, windows-early-regressions]',
                       'needs:\n      - frontend-validation\n      - windows-early-regressions'):
        workflow = 'jobs:\n  frontend-validation:\n    runs-on: ubuntu-latest\n' + (
            '  windows-x64:\n    ' + dependency + '\n    runs-on: windows-latest\n')
        assert 'frontend-validation' in workflow_job_dependencies(workflow, 'windows-x64')
    unrelated = ('jobs:\n  windows-x64:\n    needs: other-job\n'
                 '  frontend-validation:\n    runs-on: ubuntu-latest\n')
    assert 'frontend-validation' not in workflow_job_dependencies(unrelated, 'windows-x64')
    assert verify_workflow(unrelated) != []
    missing_windows = (
        'jobs:\n  frontend-validation:\n    runs-on: ubuntu-latest\n'
        '  windows-early-regressions:\n    runs-on: windows-latest\n'
        '  windows-x64:\n    needs: frontend-validation\n')
    assert any('windows-early-regressions' in error for error in verify_workflow(missing_windows))


def test_ci_requires_frontend_green_before_windows_installer():
    ci = read('.github/workflows/windows-build.yml')
    assert 'frontend-validation:' in ci
    assert 'windows-early-regressions:' in ci
    # The native installer must wait for BOTH gates to pass. A new Windows
    # preflight must never make the frontend validation optional.
    assert verify_workflow(ci) == []
    assert {'frontend-validation', 'windows-early-regressions'} <= workflow_job_dependencies(ci, 'windows-x64')
    assert 'npm ci --no-audit --no-fund' in ci
    assert 'npm run build' in ci
    assert f'BARQ_Setup_{VER}.exe' in ci
    assert 'fresh-react' in ci
    assert f'build-ok-v{VER}.marker' in ci


def test_release_version_consistent():
    assert f'#define AppVersion "{VER}"' in read('scripts/installer.iss')
    assert f"$version = '{VER}'" in read('scripts/build_windows.ps1')
    assert f'BARQ_Setup_{VER}.exe' in read('BUILD_BARQ.bat')
    assert f'set "VERSION={VER}"' in read('BUILD_WINDOWS_EXE.bat')
    lock = json.loads(read('frontend/package-lock.json'))
    assert lock['version'] == VER
    assert lock['packages']['']['version'] == VER
