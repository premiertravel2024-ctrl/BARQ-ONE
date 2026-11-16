"""Every Python release test must really run; native exits cannot be fake PASSED."""
from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
import xml.etree.ElementTree as ET

import pytest
from scripts import run_python_build_tests as runner


def _project(tmp_path: Path, count: int = 5) -> list[Path]:
    directory = tmp_path / 'tests'
    directory.mkdir()
    files = []
    for index in range(count):
        file = directory / f'test_case_{index:02d}.py'
        file.write_text(f'def test_{index}():\n    assert True\n', encoding='utf-8')
        files.append(file)
    return files


def _xml(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    node = ET.Element('testsuites')
    suite = ET.SubElement(node, 'testsuite', tests=str(count), errors='0', failures='0', skipped='0')
    for i in range(count):
        ET.SubElement(suite, 'testcase', classname='test_fake', name=f'test_{i}')
    ET.ElementTree(node).write(path, encoding='utf-8', xml_declaration=True)


def test_windows_cli_uses_forward_slash_paths_not_os_separator():
    """Windows Path.__str__ returns backslashes; pytest CLI gets canonical args.

    In the previous release this made fake_run() see zero test modules and
    caused the actual Windows installer gate's sole failing test.
    """
    root = PureWindowsPath(r'C:\Users\User Name\AppData\Local\Bq\b\stage')
    module = root / 'tests' / 'test_arabic_ملفات.py'
    assert str(module.relative_to(root)) == r'tests\test_arabic_ملفات.py'
    assert runner._pytest_test_argument(root, module) == 'tests/test_arabic_ملفات.py'
    assert runner._pytest_test_argument(root, module).startswith('tests/test_')
    with pytest.raises(ValueError):
        runner._pytest_test_argument(root, root / 'scripts' / 'run_python_build_tests.py')


def test_shards_cover_all_test_modules_once(tmp_path):
    files = _project(tmp_path, 5)
    plan = runner.test_file_shards(tmp_path, size=2)
    assert [len(chunk) for chunk in plan] == [2, 2, 1]
    assert sorted([p for chunk in plan for p in chunk]) == files
    with pytest.raises(ValueError):
        runner.test_file_shards(tmp_path, size=0)
    with pytest.raises(ValueError):
        runner.test_file_shards(tmp_path, files=[files[0], files[0]])
    with pytest.raises(ValueError):
        runner.test_file_shards(tmp_path, files=[tmp_path / 'outside.py'])


def test_native_isolation_runs_every_shard_with_junit_proof(tmp_path, monkeypatch):
    files = _project(tmp_path, 5)
    monkeypatch.setattr(runner, 'create_safe_pytest_basetemp', lambda: tmp_path / 'fixture-output')
    executed = []

    def fake_run(*, command, root, **kwargs):
        modules = [Path(x) for x in command if x.startswith('tests/test_')]
        assert modules, 'Every Python shard must send portable POSIX-style test file paths'
        report = Path(next(x.split('=', 1)[1] for x in command if x.startswith('--junitxml=')))
        _xml(report, len(modules))
        (root / 'release' / 'python-tests.log').write_text('all passed\n', encoding='utf-8')
        executed.extend(modules)
        assert '-X' in command and 'faulthandler' in command
        assert '--timeout=90' in command and '--maxfail=20' in command
        return 0

    monkeypatch.setattr(runner, 'run', fake_run)
    assert runner.run_sharded_suite(root=tmp_path, shard_size=2, require_timeout_plugin=False) == 0
    assert executed == [f.relative_to(tmp_path) for f in files]
    report = json.loads((tmp_path / 'release/python-tests-shards.json').read_text())
    assert report['success'] is True
    assert report['planned_shards'] == 3 == report['processed_shards']
    assert report['counts']['tests'] == 5
    assert ET.parse(tmp_path / 'release/python-tests.xml').getroot().get('tests') == '5'
    assert 'PASSED' in (tmp_path / 'release/python-tests.log').read_text()
    assert not (tmp_path / 'release/python-tests-failures.txt').exists()


def test_crash_after_all_passed_summary_still_blocks_installer(tmp_path, monkeypatch):
    _project(tmp_path, 3)
    monkeypatch.setattr(runner, 'create_safe_pytest_basetemp', lambda: tmp_path / 'fixture-output')
    calls = []

    def crashing_run(*, command, root, **kwargs):
        calls.append(command)
        report = Path(next(x.split('=', 1)[1] for x in command if x.startswith('--junitxml=')))
        _xml(report, 2)
        (root / 'release/python-tests.log').write_text('2 passed in 1.20s\n', encoding='utf-8')
        return 3221226255  # the actual Windows failure, even with "all passed"

    monkeypatch.setattr(runner, 'run', crashing_run)
    assert runner.run_sharded_suite(root=tmp_path, shard_size=2, require_timeout_plugin=False) != 0
    assert len(calls) == 1  # Never continue after a native process crash
    report = json.loads((tmp_path / 'release/python-tests-shards.json').read_text())
    assert report['success'] is False
    assert report['shards'][0]['exit_hex'] == '0xC000030F'
    assert '0xC000030F' in (tmp_path / 'release/python-tests-failures.txt').read_text()
    assert not (tmp_path / 'release/python-tests.xml').exists()


def test_zero_exit_without_junit_still_fails(tmp_path, monkeypatch):
    _project(tmp_path, 1)
    monkeypatch.setattr(runner, 'create_safe_pytest_basetemp', lambda: tmp_path / 'fixture-output')

    def run_without_report(*, root, **kwargs):
        (root / 'release/python-tests.log').write_text('1 passed in 1.0s\n', encoding='utf-8')
        return 0

    monkeypatch.setattr(runner, 'run', run_without_report)
    assert runner.run_sharded_suite(root=tmp_path, require_timeout_plugin=False) != 0
    assert 'produced no JUnit' in (tmp_path / 'release/python-tests-failures.txt').read_text()


def test_build_still_uses_python_test_gate_and_refuses_nonzero():
    root = Path(__file__).resolve().parents[1]
    build = (root / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    script = (root / 'scripts/run_python_build_tests.py').read_text(encoding='utf-8')
    assert '& $python -m scripts.run_python_build_tests' in build
    assert 'if ($LASTEXITCODE -ne 0)' in build
    assert 'run_sharded_suite()' in script
    assert "'--timeout=90'" in script
    assert 'python-tests-shards.json' in script
