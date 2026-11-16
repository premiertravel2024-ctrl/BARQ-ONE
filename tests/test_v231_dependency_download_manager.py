"""Regression: unstable downloads never bypass BARQ's required release gates."""
from pathlib import Path
from scripts import build_dependency_manager as deps

ROOT = Path(__file__).resolve().parents[1]


def test_cache_shared_across_staged_folders(tmp_path):
    env = {'LOCALAPPDATA': str(tmp_path)}
    assert deps.cache_root(env) == tmp_path / 'Bq' / 'deps'
    assert 'build' not in str(deps.cache_root(env))


def test_permanent_dependency_error_never_retried(tmp_path):
    calls = []
    def fake(command, *, cwd, env, log):
        calls.append(command)
        return deps.Result(1, 'npm error code ERESOLVE')
    r = deps._execute_attempts(['npm', 'ci'], cwd=tmp_path, env={}, log=tmp_path / 't.log',
                               name='demo', runner=fake, sleep=lambda _: None)
    assert r.returncode == 1
    assert len(calls) == 1


def test_transient_network_error_retries_and_success(tmp_path):
    calls = []
    def fake(command, *, cwd, env, log):
        calls.append(command)
        return deps.Result(1, 'ETIMEDOUT') if len(calls) == 1 else deps.Result(0, 'ok')
    r = deps._execute_attempts(['npm', 'ci'], cwd=tmp_path, env={}, log=tmp_path / 't.log',
                               name='demo', runner=fake, sleep=lambda _: None)
    assert r.returncode == 0
    assert len(calls) == 2


def test_no_retry_when_unknown_error(tmp_path):
    calls = []
    def fake(command, *, cwd, env, log):
        calls.append(command)
        return deps.Result(1, 'invalid command')
    r = deps._execute_attempts(['npm'], cwd=tmp_path, env={}, log=tmp_path / 't.log',
                               name='demo', runner=fake)
    assert r.returncode != 0 and len(calls) == 1


def test_npm_retains_lock_and_integrity_and_fallback(tmp_path, monkeypatch):
    (tmp_path / 'frontend').mkdir()
    import shutil
    shutil.copy2(ROOT / 'frontend' / 'package-lock.json', tmp_path / 'frontend' / 'package-lock.json')
    shutil.copy2(ROOT / 'frontend' / 'package.json', tmp_path / 'frontend' / 'package.json')
    monkeypatch.setattr(deps, 'find_npm', lambda env: 'npm.cmd')
    calls = []
    def fake(command, *, cwd, env, log):
        calls.append((command, env))
        if '--offline' in command:
            return deps.Result(0, 'added 10 packages')
        return deps.Result(1, 'fetch failed ECONNRESET')
    assert deps.install_frontend(tmp_path, env={'LOCALAPPDATA': str(tmp_path / 'shared')},
                                 runner=fake, sleep=lambda _: None)
    assert len(calls) == 4  # 3 transient attempts and one offline
    assert all(c[0][1] == 'ci' and '--include=dev' in c[0] for c in calls)
    assert '--offline' in calls[-1][0]
    # Windows uses backslashes; compare path components instead of POSIX text.
    assert all(Path(c[1]['npm_config_cache']) == tmp_path / 'shared' / 'Bq' / 'deps' / 'npm' for c in calls)


def test_python_is_installed_once_in_isolated_venv_with_shared_cache(tmp_path):
    exe = tmp_path / '.buildvenv' / 'Scripts' / 'python.exe'
    exe.parent.mkdir(parents=True)
    exe.write_text('fake')
    calls = []
    def fake(command, *, cwd, env, log):
        calls.append((command, env))
        return deps.Result(0, 'installed')
    assert deps.install_python(tmp_path, exe, env={'LOCALAPPDATA': str(tmp_path)},runner=fake)
    cmd, env = calls[0]
    assert cmd[0] == str(exe) and cmd[1:4] == ['-m', 'pip', 'install']
    assert '--upgrade' not in cmd
    assert 'requirements-desktop.txt' in ' '.join(cmd)
    assert 'requirements-computer-control.txt' in ' '.join(cmd)
    assert Path(env['PIP_CACHE_DIR']) == tmp_path / 'Bq' / 'deps' / 'pip'
    assert len(calls) == 1


def test_windows_script_preserves_release_tests_and_no_second_wake_download():
    source = (ROOT / 'scripts' / 'build_windows.ps1').read_text(encoding='utf-8')
    assert "build_dependency_manager.py') --frontend" in source
    assert "build_dependency_manager.py') --python" in source
    assert source.count("-m pip install --disable-pip-version-check") == 0
    assert source.index('build_dependency_manager.py') < source.index('scripts.run_python_build_tests')
    assert source.index('scripts.run_python_build_tests') < source.index("'-m', 'PyInstaller'")
    assert 'smoke_install.ps1' in source and 'verify-esbuild.cjs' in source


def test_build_failure_diagnostics_include_download_logs():
    text = (ROOT / 'scripts/build_short_path.py').read_text(encoding='utf-8')
    assert "log.name.startswith('dependency-')" in text
    assert "diagnostic.name.startswith('dependency-')" in text


def test_logged_subprocess_reports_real_stdout_and_failure(tmp_path):
    import os
    import sys
    command = [sys.executable, '-c', 'print("build command ran"); raise SystemExit(7)']
    report = tmp_path / 'dependency-test.log'
    result = deps.run_logged(command, cwd=tmp_path, env=dict(os.environ),log=report)
    assert result.returncode == 7
    assert 'build command ran' in result.output
    assert 'EXIT CODE: 7' in report.read_text(encoding='utf-8')


def test_secret_in_registry_url_is_redacted():
    original = 'request https://user:password@registry.example/private?access_token=abc123 failed'
    safe = deps.redact(original)
    assert 'password' not in safe
    assert 'abc123' not in safe
    assert '[REDACTED]' in safe


def test_download_doctor_is_present_and_build_uses_early_check():
    assert (ROOT / 'CHECK_BARQ_DOWNLOADS.bat').is_file()
    script = (ROOT / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert "build_dependency_manager.py') --check" in script
    assert script.index("build_dependency_manager.py') --check") < script.index('build_short_path.py')
