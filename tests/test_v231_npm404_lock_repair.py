"""Regression for BARQ release blocked by an impossible npm 404 tarball.

Real failure: the lock advertised is-core-module@2.18.2 with integrity of
published 2.17.0, and falsely claimed resolve@1.22.13 required ^2.18.2.
No CI test should need registry/network to expose such a bad lockfile.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from scripts import build_dependency_manager as deps
from scripts.verify_frontend_lock import verify

ROOT = Path(__file__).resolve().parents[1]


def staging(tmp_path):
    front = tmp_path / 'frontend'
    front.mkdir()
    for name in ('package.json', 'package-lock.json'):
        shutil.copy2(ROOT / 'frontend' / name, front / name)
    return front


def test_published_is_core_module_lock_matches_resolve_contract():
    assert verify(ROOT) == []
    data = json.loads((ROOT / 'frontend' / 'package-lock.json').read_text(encoding='utf-8'))
    assert data['packages']['node_modules/resolve']['dependencies']['is-core-module'] == '^2.17.0'
    assert data['packages']['node_modules/is-core-module']['version'] == '2.17.0'


def test_old_nonexistent_2182_tarball_detected_before_npm(tmp_path):
    front = staging(tmp_path)
    path = front / 'package-lock.json'
    source = path.read_text()
    source = source.replace('"version": "2.17.0"', '"version": "2.18.2"')
    source = source.replace('is-core-module-2.17.0.tgz', 'is-core-module-2.18.2.tgz')
    source = source.replace('"is-core-module": "^2.17.0"', '"is-core-module": "^2.18.2"')
    path.write_text(source)
    issues = verify(tmp_path)
    assert any('vetted published package' in issue for issue in issues)
    assert any('published dependency' in issue for issue in issues)


def test_reject_nonmatching_package_url(tmp_path):
    front = staging(tmp_path)
    path = front / 'package-lock.json'
    data = json.loads(path.read_text())
    data['packages']['node_modules/is-core-module']['resolved'] = (
        'https://registry.npmjs.org/is-core-module/-/is-core-module-9.9.9.tgz'
    )
    path.write_text(json.dumps(data))
    assert any('registry tarball URL does not match' in issue for issue in verify(tmp_path))


def test_404_is_permanent_and_not_retried(tmp_path):
    seen = []
    def fake(command, *, cwd, env, log):
        seen.append(command)
        return deps.Result(1, 'npm error code E404\nnpm error 404 Not Found - GET https://registry.npmjs.org/is-core-module/-/is-core-module-2.18.2.tgz')
    result = deps._execute_attempts(['npm', 'ci'], cwd=tmp_path, env={}, log=tmp_path / 'npm.log',
                                    name='E404', runner=fake, sleep=lambda _: None)
    assert result.returncode == 1
    assert deps.classify(result) == 'permanent'
    assert len(seen) == 1


def test_build_manager_scripts_run_directly_outside_repo_with_isolated_python(tmp_path):
    command = [sys.executable, '-I', str(ROOT / 'scripts' / 'build_dependency_manager.py'), '--check']
    response = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert response.returncode == 0, response.stdout + response.stderr
    assert '[BARQ NPM LOCK] PASS' in response.stdout


def test_build_preflight_checks_lock_before_downloads():
    script = (ROOT / 'scripts' / 'build_dependency_manager.py').read_text(encoding='utf-8')
    assert 'lock_issues = verify_npm_lock(ROOT)' in script
    assert script.index('issues = verify_npm_lock(root)') < script.index('args = [npm,')
    assert 'npm' in script and 'ci' in script
