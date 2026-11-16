"""Windows release suite must be observable, bounded and never swallow failures."""
import sys
from pathlib import Path
from scripts.run_python_build_tests import run


def test_monitored_pytest_runner_success_and_last_test(tmp_path):
    code = "print('tests/test_x.py::test_works PASSED [100%]', flush=True)"
    assert run(command=[sys.executable, '-u', '-c', code], root=tmp_path,
               idle_timeout=3, total_timeout=5) == 0
    assert 'test_works' in (tmp_path / 'release/python-tests-last-test.txt').read_text()
    assert 'PASSED' in (tmp_path / 'release/python-tests.log').read_text()


def test_monitored_pytest_runner_reports_real_failure(tmp_path):
    code = "import sys; print('tests/test_x.py::test_fails FAILED [100%]',flush=True);sys.exit(7)"
    assert run(command=[sys.executable, '-u', '-c', code], root=tmp_path,
               idle_timeout=3, total_timeout=5) == 7
    assert 'FAILED' in (tmp_path / 'release/python-tests.log').read_text()


def test_monitored_pytest_runner_kills_silent_hang(tmp_path):
    code = "import time;print('tests/test_x.py::test_stuck',flush=True);time.sleep(10)"
    assert run(command=[sys.executable, '-u', '-c', code], root=tmp_path,
               idle_timeout=3.0, total_timeout=8) == 124
    assert 'test_stuck' in (tmp_path / 'release/python-tests-last-test.txt').read_text()
    assert 'TIMEOUT' in (tmp_path / 'release/python-tests.log').read_text()
    assert 'test_stuck' in (tmp_path / 'release/python-tests-failures.txt').read_text()


def test_windows_powershell_gate_still_requires_success(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = (root / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert "run_python_build_tests.py" in script
    assert "if ($LASTEXITCODE -ne 0)" in script
    assert "throw \"Python tests failed (exit $LASTEXITCODE)\"" in script
    assert "--timeout=90" in (root/'scripts/run_python_build_tests.py').read_text()
    assert 'pytest-timeout' in (root/'requirements.txt').read_text()


def test_monitored_runner_reports_all_failures_together(tmp_path):
    # Simulate pytest summary, without running or skipping the actual suite.
    source = (
        "import sys; "
        "print('FAILED tests/test_a.py::test_a - AssertionError',flush=True); "
        "print('FAILED tests/test_b.py::test_b - AssertionError',flush=True); "
        "sys.exit(1)"
    )
    assert run(command=[sys.executable, '-u', '-c', source], root=tmp_path,
               idle_timeout=3, total_timeout=5) == 1
    failure_file = tmp_path / 'release/python-tests-failures.txt'
    assert failure_file.read_text(encoding='utf-8').splitlines() == [
        'tests/test_a.py::test_a', 'tests/test_b.py::test_b'
    ]
    # Follow-up success must not leave an old failure list around.
    assert run(command=[sys.executable, '-u', '-c', "print('ok')"], root=tmp_path,
               idle_timeout=3, total_timeout=5) == 0
    assert not failure_file.exists()

def test_release_suite_collects_multiple_failures_before_blocking():
    root = Path(__file__).resolve().parents[1]
    runner = (root / 'scripts/run_python_build_tests.py').read_text(encoding='utf-8')
    assert "'--maxfail=20'" in runner
    assert "python-tests-failures.txt" in runner
