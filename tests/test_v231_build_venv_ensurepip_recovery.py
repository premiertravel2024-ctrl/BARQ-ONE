"""Regression: Python 3.11 ensurepip exit 1 must not strand the BARQ installer."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import create_build_venv as venv_build  # noqa: E402


def test_build_windows_uses_verified_recovery_without_skipping_gates():
    builder = (ROOT / 'scripts' / 'build_windows.ps1').read_text(encoding='utf-8')
    assert "'create_build_venv.py'" in builder
    assert "Invoke-Step 'Creating isolated Python 3.11 build environment'" in builder
    assert '$python -m pip --version' in builder
    assert builder.index('create_build_venv.py') < builder.index('npm ci --no-audit --no-fund --include=dev')
    assert builder.index('create_build_venv.py') < builder.index('Installing Python desktop dependencies')
    assert builder.index('Installing Python desktop dependencies') < builder.index('scripts.run_python_build_tests')
    assert builder.index('scripts.run_python_build_tests') < builder.index("'-m', 'PyInstaller'")


def test_venv_does_not_remove_any_other_folder(tmp_path):
    other = tmp_path / 'Documents'
    other.mkdir()
    (other / 'keep.txt').write_text('safe', encoding='utf-8')
    try:
        venv_build._safe_remove_venv(other, tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError('must not delete outside .buildvenv')
    assert (other / 'keep.txt').read_text(encoding='utf-8') == 'safe'


def test_venv_symlink_will_not_be_deleted(tmp_path):
    target = tmp_path / 'valuable'
    target.mkdir()
    (target / 'keep.txt').write_text('safe', encoding='utf-8')
    link = tmp_path / '.buildvenv'
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        return  # Windows often restricts symlink creation on CI
    try:
        venv_build._safe_remove_venv(link, tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError('symlinked .buildvenv should be rejected')
    assert (target / 'keep.txt').is_file()


def test_when_ensurepip_fails_uv_bootstraps_and_verifies(monkeypatch, tmp_path):
    monkeypatch.setattr(venv_build.sys, 'version_info', (3, 11, 9))
    monkeypatch.setattr(venv_build, '_uv_executable', lambda env: 'uv.exe')
    b = venv_build.BuildVenv(tmp_path, base_python='python311.exe')
    seen = []
    def run(label, args, *, timeout=300):
        seen.append((label, args))
        return not label.startswith('Standard')
    monkeypatch.setattr(b, 'run', run)
    monkeypatch.setattr(b, 'verify', lambda: True)
    assert b.create()
    assert seen[0][1][:3] == ['python311.exe', '-m', 'venv']
    assert any(args[:5] == ['uv.exe', 'venv', '--seed', '--python', 'python311.exe'] for _, args in seen)
    assert not any('pip --python' in label for label, _ in seen)


def test_all_bootstrap_failures_still_block_release(monkeypatch, tmp_path):
    monkeypatch.setattr(venv_build.sys, 'version_info', (3, 11, 9))
    monkeypatch.setattr(venv_build, '_uv_executable', lambda env: None)
    b = venv_build.BuildVenv(tmp_path, base_python='python311.exe')
    commands = []
    monkeypatch.setattr(b, 'run', lambda label, args, **kw: (commands.append(args), label.startswith('Fallback: create'))[1])
    assert b.create() is False
    assert any('--without-pip' in args for args in commands)
    assert any('--python' in args for args in commands)
    assert 'FAILED' in b.log_path.read_text(encoding='utf-8')


def test_fallback_uses_base_pip_only_targeted_at_venv(monkeypatch, tmp_path):
    monkeypatch.setattr(venv_build.sys, 'version_info', (3, 11, 9))
    monkeypatch.setattr(venv_build, '_uv_executable', lambda env: None)
    b = venv_build.BuildVenv(tmp_path, base_python='python311.exe')
    seen = []
    def run(label, args, **kw):
        seen.append((label, args))
        return label.startswith('Fallback')
    monkeypatch.setattr(b, 'run', run)
    monkeypatch.setattr(b, 'verify', lambda: True)
    assert b.create()
    pip_invocations = [args for _, args in seen if '-m' in args and 'pip' in args]
    assert pip_invocations
    assert pip_invocations[-1][:4] == ['python311.exe', '-m', 'pip', '--python']
    assert pip_invocations[-1][4] == str(tmp_path / '.buildvenv')


def test_failure_report_propagates_out_of_short_path():
    source = (ROOT / 'scripts' / 'build_short_path.py').read_text(encoding='utf-8')
    assert "log.name.startswith('python-venv-')" in source
    assert "diagnostic.name.startswith('python-venv-')" in source
