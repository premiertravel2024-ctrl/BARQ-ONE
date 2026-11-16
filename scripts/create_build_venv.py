"""Build a verified, isolated Python venv with recovery from Windows ensurepip failures.

Called by build_windows.ps1 using `py -3.11 scripts/create_build_venv.py`.
The fallback never installs into the global Python and never disables release gates.
Keep full diagnostics in release/python-venv-setup.log.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def _clean_python_env() -> dict[str, str]:
    env = os.environ.copy()
    # These overrides can make venv/ensurepip import packages from an unrelated
    # Python installation and are not required for a correctly located launcher.
    for key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', '__PYVENV_LAUNCHER__'):
        env.pop(key, None)
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    # Avoid the frequently broken Windows user TEMP used by ensurepip's wheel
    # extraction. This path is intentionally short, writable and per-user.
    base = Path(env.get('LOCALAPPDATA') or tempfile.gettempdir()) / 'Bq' / 'tmp'
    base.mkdir(parents=True, exist_ok=True)
    env['TEMP'] = str(base)
    env['TMP'] = str(base)
    env['TMPDIR'] = str(base)
    return env


def _python_in(venv: Path) -> Path:
    return venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def _safe_remove_venv(path: Path, root: Path) -> None:
    if path != root / '.buildvenv':
        raise ValueError('Refusing to remove a directory other than the build venv')
    if path.is_symlink():
        raise ValueError('Refusing to remove a symlinked build venv')
    if os.name == 'nt' and path.exists():
        attributes = path.stat().st_file_attributes
        if attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT (junction)
            raise ValueError('Refusing to remove a reparse-point build venv')
    if path.exists():
        shutil.rmtree(path)


def _uv_executable(env: dict[str, str]) -> str | None:
    found = shutil.which('uv', path=env.get('PATH'))
    if found:
        return found
    # The BARQ toolkit installs uv under ~/.local/bin; a running build process
    # often has stale PATH even after the installation succeeded.
    profile = env.get('USERPROFILE')
    if profile:
        candidate = Path(profile) / '.local' / 'bin' / 'uv.exe'
        if candidate.is_file():
            return str(candidate)
    return None


class BuildVenv:
    def __init__(self, root: Path, *, base_python: str | None = None):
        self.root = root.resolve()
        self.path = self.root / '.buildvenv'
        self.base_python = base_python or sys.executable
        self.log_path = self.root / 'release' / 'python-venv-setup.log'
        self.env = _clean_python_env()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(
            f'BARQ isolated Python build env | {time.strftime("%Y-%m-%d %H:%M:%S")}\n'
            f'Interpreter: {self.base_python}\n'
            f'Project root: {self.root}\n'
            f'TEMP/TMP: {self.env["TEMP"]}\n', encoding='utf-8',
        )

    def _append(self, text: str) -> None:
        with self.log_path.open('a', encoding='utf-8') as f:
            f.write(text + '\n')

    def run(self, label: str, args: list[str], *, timeout: int = 300) -> bool:
        self._append(f'\n=== {label} ===\nCOMMAND: {args!r}')
        try:
            result = subprocess.run(
                args, cwd=self.root, env=self.env, capture_output=True,
                text=True, encoding='utf-8', errors='replace', timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._append(f'FAILED to start/finish: {exc}')
            print(f'[BARQ PYTHON VENV] {label}: {exc}', flush=True)
            return False
        output = '\n'.join(part for part in (result.stdout, result.stderr) if part)
        self._append(output[-40000:] if output else '(no output)')
        self._append(f'EXIT CODE: {result.returncode}')
        print(f'[BARQ PYTHON VENV] {label}: exit {result.returncode}', flush=True)
        if result.returncode and output:
            print(output[-3500:], flush=True)
        return result.returncode == 0

    def verify(self) -> bool:
        python = _python_in(self.path)
        if not python.is_file():
            self._append('FAILED: venv interpreter does not exist')
            return False
        probe = (
            'import sys, pip; '
            'assert sys.version_info[:2] == (3, 11), "Expected Python 3.11"; '
            'assert sys.prefix != sys.base_prefix, "Not inside a virtual environment"; '
            'print("Python", sys.version.split()[0], "pip", pip.__version__, "venv", sys.prefix)'
        )
        return self.run('Verify Python 3.11 + pip isolation', [str(python), '-c', probe], timeout=40)

    def create(self) -> bool:
        if sys.version_info[:2] != (3, 11):
            # The build wrapper invokes us through py -3.11, never auto-select
            # another Python version for a release.
            self._append(f'ERROR: expected Python 3.11, got {sys.version_info[:2]}')
            print('[BARQ PYTHON VENV] Python 3.11 is required for the Windows release.')
            return False
        _safe_remove_venv(self.path, self.root)
        if self.run('Standard venv with ensurepip',
                    [self.base_python, '-m', 'venv', str(self.path)]) and self.verify():
            print('[BARQ PYTHON VENV] PASS: standard venv is ready.', flush=True)
            return True
        self._append('Standard ensurepip failed; trying uv seed as a separate recovery method')
        print('[BARQ PYTHON VENV] ensurepip failed; trying uv recovery.', flush=True)

        uv = _uv_executable(self.env)
        if uv:
            _safe_remove_venv(self.path, self.root)
            if self.run('Fallback: uv venv --seed (no global pip modification)',
                        [uv, 'venv', '--seed', '--python', self.base_python, str(self.path)]) and self.verify():
                print('[BARQ PYTHON VENV] PASS: uv seeded isolated venv.', flush=True)
                return True
        else:
            self._append('uv missing: cannot attempt uv-based recovery')

        _safe_remove_venv(self.path, self.root)
        if self.run('Fallback: create venv without ensurepip',
                    [self.base_python, '-m', 'venv', '--without-pip', str(self.path)]):
            # `pip --python` bootstraps the target venv, not the host Python.
            # This requires a functioning base pip; if unavailable, fail closed.
            if self.run('Fallback: seed target venv using base pip --python',
                        [self.base_python, '-m', 'pip', '--python', str(self.path),
                         'install', '--disable-pip-version-check', 'pip']) and self.verify():
                print('[BARQ PYTHON VENV] PASS: target venv bootstrapped with pip.', flush=True)
                return True
        # Diagnostics only: these checks do not install into the base interpreter.
        self.run('Diagnostic: base Python ensurepip',
                 [self.base_python, '-m', 'ensurepip', '--version'], timeout=30)
        self.run('Diagnostic: base Python pip',
                 [self.base_python, '-m', 'pip', '--version'], timeout=30)
        self._append('FAILED: all venv methods failed. No EXE packaging attempted.')
        print('[BARQ PYTHON VENV] FAILED. Read release\\python-venv-setup.log. '
              'Check Python 3.11 installation, Windows Defender, disk space, and uv.', flush=True)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true',
                        help='Test venv creation in a temporary folder, no BARQ build')
    args = parser.parse_args(argv)
    if args.probe:
        base = Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()) / 'Bq' / 'venv_probe'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base, prefix='p') as directory:
            # Copy log to a durable location so failure evidence survives cleanup.
            trial = BuildVenv(Path(directory))
            ok = trial.create()
            durable = ROOT / 'release' / 'python-venv-probe.log'
            durable.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(trial.log_path, durable)
            print(f'[BARQ PYTHON VENV] Probe log: {durable}', flush=True)
            return 0 if ok else 1
    builder = BuildVenv(ROOT)
    return 0 if builder.create() else 1


if __name__ == '__main__':
    raise SystemExit(main())
