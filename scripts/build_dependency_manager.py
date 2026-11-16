"""Stable, resumable build dependency downloads for BARQ's short-path Windows stages.

Separate project-scoped *installation* from cross-build *artifact caches*.
Does not weaken npm's lockfile, pip version constraints, or release tests.
Never deletes a shared cache and never logs credentials or environment secrets.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
# Direct execution by build_windows.ps1 must also resolve the sibling scripts package.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Native downloads can fail through Windows proxy/VPN/DNS fluctuations; distinguish
# those failures from broken manifests / missing wheels / incompatible versions.
TRANSIENT = re.compile(
    r"(?i)(ETIMEDOUT|ECONNRESET|ECONNREFUSED|EAI_AGAIN|ENOTFOUND|EHOSTUNREACH|"
    r"ERR_SOCKET_TIMEOUT|ERR_NETWORK|fetch failed|network timeout|"
    r"read timed out|connection (?:reset|aborted|timed out|refused)|"
    r"temporary failure in name resolution|name or service not known|"
    r"SSLError|SSL: CERTIFICATE_VERIFY_FAILED|ProxyError|"
    r"429 Too Many Requests|502 Bad Gateway|503 Service Unavailable|504 Gateway Timeout)"
)
# Version resolution and manifest errors must not loop or receive unsafe workarounds.
PERMANENT = re.compile(
    r"(?i)(E404|ETARGET|404 Not Found|ERESOLVE|EINTEGRITY|ENOTSUP|Unsupported engine|"
    r"No matching distribution found|Could not find a version that satisfies|"
    r"npm ERR! code EUSAGE|not in sync with package-lock|"
    r"HASH MISMATCH|HashMismatch|invalid wheel)"
)


def redact(text: str) -> str:
    """Avoid leaking credentials included in private registry/proxy error text."""
    text = re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', text)
    text = re.sub(r'(?i)([?&](?:token|access_token|api_key|auth|password)=)[^&\s]+',
                  r'\1[REDACTED]', text)
    return text


@dataclass
class Result:
    returncode: int
    output: str


def cache_root(env: dict[str, str]) -> Path:
    override = env.get('BARQ_DEP_CACHE')
    if override:
        return Path(override).expanduser()
    home = env.get('LOCALAPPDATA') or env.get('XDG_CACHE_HOME')
    if home:
        return Path(home) / 'Bq' / 'deps'
    return Path.home() / '.cache' / 'barq' / 'deps'


def classify(result: Result) -> str:
    if result.returncode == 0:
        return 'success'
    if PERMANENT.search(result.output):
        return 'permanent'
    if TRANSIENT.search(result.output):
        return 'transient'
    return 'unknown'


def run_logged(command: list[str], *, cwd: Path, env: dict[str, str], log: Path,
               timeout: int = 1200) -> Result:
    """Record full output and show download progress without keeping huge stdout in RAM."""
    with log.open('a', encoding='utf-8') as stream:
        stream.write(f'\nCOMMAND: {command[0]} [args hidden: see build script; no secrets] START\n')
        stream.flush()
        try:
            process = subprocess.Popen(command, cwd=str(cwd), env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as error:
            stream.write(f'EXECUTION ERROR: {error}\n')
            return Result(127, str(error))
        deadline = time.monotonic() + timeout
        # Use a background reader to avoid blocking forever waiting for a line;
        # pip/npm normally emit line-delimited output but progress may use CR.
        import threading
        from collections import deque
        recent: deque[str] = deque(maxlen=180)

        def consume() -> None:
            assert process.stdout is not None
            for raw in iter(process.stdout.readline, b''):
                line = redact(raw.decode('utf-8', errors='replace').rstrip('\r\n')[:4000])
                recent.append(line)
                stream.write(line + '\n')
                stream.flush()
                if ('error' in line.lower() or 'added ' in line or 'Successfully installed' in line):
                    print('[BARQ DEPS] ' + line[:280], flush=True)

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        try:
            process.wait(timeout=max(1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            reader.join(timeout=5)
            stream.write(f'TIMEOUT: {timeout} seconds\n')
            return Result(124, '\n'.join(recent) + '\nnetwork timeout')
        reader.join(timeout=10)
        stream.write(f'EXIT CODE: {process.returncode}\n')
        return Result(process.returncode, '\n'.join(recent))


def _execute_attempts(command: list[str], *, cwd: Path, env: dict[str, str],
                      log: Path, name: str, runner: Callable[..., Result] = run_logged,
                      max_attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> Result:
    last = Result(1, 'not attempted')
    for i in range(1, max_attempts + 1):
        print(f'[BARQ DEPS] {name}: attempt {i}/{max_attempts} (shared cache)', flush=True)
        last = runner(command, cwd=cwd, env=env, log=log)
        if last.returncode == 0:
            print(f'[BARQ DEPS] {name}: PASS', flush=True)
            return last
        category = classify(last)
        print(f'[BARQ DEPS] {name}: {category} failure, exit {last.returncode}', flush=True)
        if category != 'transient' or i == max_attempts:
            break
        sleep(min(2 ** (i - 1), 8))
    return last


def find_npm(env: dict[str, str]) -> str | None:
    found = shutil.which('npm.cmd' if os.name == 'nt' else 'npm', path=env.get('PATH'))
    if found:
        return found
    if os.name != 'nt':
        return None
    # BARQ toolkit/winget installers may update the user or machine PATH while
    # the current cmd.exe still has an older PATH snapshot.
    candidates = []
    for name, parts in (
        ('ProgramFiles', ('nodejs', 'npm.cmd')),
        ('ProgramFiles(x86)', ('nodejs', 'npm.cmd')),
        ('LOCALAPPDATA', ('Programs', 'nodejs', 'npm.cmd')),
        ('APPDATA', ('npm', 'npm.cmd')),
        ('USERPROFILE', ('scoop', 'apps', 'nodejs-lts', 'current', 'npm.cmd')),
    ):
        if env.get(name):
            candidates.append(Path(env[name]).joinpath(*parts))
    return next((str(path) for path in candidates if path.is_file()), None)


def _env_with_cache(env: dict[str, str], cache: Path) -> dict[str, str]:
    result = env.copy()
    result['PYTHONUTF8'] = '1'
    result['PYTHONIOENCODING'] = 'utf-8'
    result['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    result['PIP_CACHE_DIR'] = str(cache / 'pip')
    result['npm_config_cache'] = str(cache / 'npm')
    # Noninteractive build. Overrides a stale machine-global production setting.
    result['npm_config_production'] = 'false'
    return result


def install_frontend(root: Path, *, env: dict[str, str] | None = None,
                     runner: Callable[..., Result] = run_logged,
                     sleep: Callable[[float], None] = time.sleep) -> bool:
    env = dict(os.environ if env is None else env)
    cache = cache_root(env)
    cache.mkdir(parents=True, exist_ok=True)
    (cache / 'npm').mkdir(exist_ok=True)
    log = root / 'release' / 'dependency-npm.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('BARQ locked npm install; cache persists between builds\n', encoding='utf-8')
    frontend = root / 'frontend'
    from scripts.verify_frontend_lock import verify as verify_npm_lock
    issues = verify_npm_lock(root)
    if issues:
        message = '\n'.join('[BARQ NPM LOCK] ' + issue for issue in issues)
        with log.open('a', encoding='utf-8') as stream:
            stream.write('LOCKFILE PREFLIGHT FAILED:\n' + message + '\n')
        print(message, flush=True)
        return False
    npm = find_npm(env)
    if not npm:
        print('[BARQ DEPS] Node/npm not on PATH; install Node LTS and restart terminal.', flush=True)
        return False
    env = _env_with_cache(env, cache)
    args = [npm, 'ci', '--no-audit', '--no-fund', '--include=dev',
            '--prefer-offline', '--fetch-retries=4', '--fetch-retry-mintimeout=2000',
            '--fetch-retry-maxtimeout=15000']
    first = _execute_attempts(args, cwd=frontend, env=env, log=log,
                              name='Locked React dependencies', runner=runner, sleep=sleep)
    if first.returncode == 0:
        return True
    # Exact same lockfile and integrity verification; offline only if the online
    # attempt failed due to connectivity, never bypass version/integrity checks.
    if classify(first) == 'transient':
        print('[BARQ DEPS] Network unstable. Trying the persistent npm cache offline.', flush=True)
        retry = runner(args + ['--offline'], cwd=frontend, env=env, log=log)
        if retry.returncode == 0:
            return True
    print(f'[BARQ DEPS] Frontend dependency install FAILED. See {log}', flush=True)
    return False


def install_python(root: Path, venv_python: Path, *, env: dict[str, str] | None = None,
                   runner: Callable[..., Result] = run_logged,
                   sleep: Callable[[float], None] = time.sleep) -> bool:
    env = dict(os.environ if env is None else env)
    cache = cache_root(env)
    cache.mkdir(parents=True, exist_ok=True)
    (cache / 'pip').mkdir(exist_ok=True)
    log = root / 'release' / 'dependency-pip.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('BARQ isolated Python dependency install; shared cache; no global pip upgrade\n', encoding='utf-8')
    if not venv_python.is_file():
        print(f'[BARQ DEPS] Missing build Python: {venv_python}', flush=True)
        return False
    env = _env_with_cache(env, cache)
    # The same single resolver invocation avoids repeated PyPI resolutions of
    # numpy/voice/gui deps and install order conflicts. No --upgrade pip network gate.
    args = [str(venv_python), '-m', 'pip', 'install', '--disable-pip-version-check',
            '--retries', '5', '--timeout', '60', '--prefer-binary',
            '--find-links', str(root / 'vendor' / 'windows-wheels'),
            '-r', str(root / 'requirements-desktop.txt'),
            '-r', str(root / 'requirements-computer-control.txt')]
    result = _execute_attempts(args, cwd=root, env=env, log=log, name='Python desktop and Windows tools',
                               runner=runner, sleep=sleep)
    if result.returncode == 0:
        return True
    if classify(result) == 'transient' and (root / 'vendor' / 'windows-wheels').is_dir():
        # Only use verified local directory supplied by BARQ's existing wheel
        # preparation script; --no-index never installs a partially resolved set.
        retry = runner(args + ['--no-index'], cwd=root, env=env, log=log)
        if retry.returncode == 0:
            return True
    print(f'[BARQ DEPS] Python dependency install FAILED. See {log}', flush=True)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Inspect prerequisite paths and persistent caches, no downloads')
    parser.add_argument('--frontend', action='store_true')
    parser.add_argument('--python', action='store_true')
    parser.add_argument('--python-executable')
    args = parser.parse_args(argv)
    if args.check:
        env = dict(os.environ)
        cache = cache_root(env)
        npm = find_npm(env)
        print('[BARQ DEPS] Shared cache:', cache)
        print('[BARQ DEPS] npm:', npm or 'MISSING / restart terminal after Node installation')
        print('[BARQ DEPS] Python:', sys.executable, sys.version.split()[0])
        print('[BARQ DEPS] locked npm:', (ROOT / 'frontend' / 'package-lock.json').is_file())
        print('[BARQ DEPS] Python requirements:', all((ROOT / name).is_file() for name in
              ('requirements-desktop.txt', 'requirements-computer-control.txt')))
        from scripts.verify_frontend_lock import verify as verify_npm_lock
        lock_issues = verify_npm_lock(ROOT)
        for issue in lock_issues:
            print('[BARQ NPM LOCK] FAIL:', issue, flush=True)
        if not lock_issues:
            print('[BARQ NPM LOCK] PASS: checked metadata, URLs and sha512 digests.', flush=True)
        free = shutil.disk_usage(ROOT).free // (1024 ** 3)
        print(f'[BARQ DEPS] Free project-drive space: {free} GiB')
        return 0 if npm and not lock_issues and free >= 1 else 1
    if not args.frontend and not args.python:
        parser.error('Specify --frontend or --python')
    if args.python and not args.python_executable:
        parser.error('--python-executable is required with --python')
    ok = True
    if args.frontend:
        ok = install_frontend(ROOT) and ok
    if args.python:
        ok = install_python(ROOT, Path(args.python_executable)) and ok
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
