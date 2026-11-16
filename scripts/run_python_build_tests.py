"""Bounded, observable Windows pytest release gate.

Never converts failed tests to skipped tests. If a test freezes, stop the
pytest process tree, keep a readable log, and block the installer.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path, PurePath
import queue
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
# Windows builds execute this file directly from scripts/ inside a staged tree.
# In that mode Python puts scripts/ (NOT the project root) on sys.path, so
# importing services.device_index failed before pytest even started.
# Resolve from this script's real location, not the shell's working directory.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RELEASE = ROOT / 'release'
INACTIVITY_TIMEOUT = 120  # no output from a single test / subprocess
TOTAL_TIMEOUT = 1200  # hard upper bound even if output trickles in
TEST_NAME = re.compile(r'(tests[\\/][^\r\n]+?::[^\s\r\n]+)')



def create_safe_pytest_basetemp(home: Path | None = None) -> Path:
    """Make an ephemeral fixture directory outside the protected AppData tree.

    Windows builds are staged under LOCALAPPDATA/Bq/b, and default pytest
    fixtures normally live under LOCALAPPDATA/Temp. The crawler correctly
    refuses AppData, except for a narrowly consented real Temp subtree. Tests
    of normal private indexing must not depend on those protected locations.
    Keep the release test gate intact; move *only pytest-generated fixtures*.
    """
    from services.device_index import _safe_path
    from computer_control.safety.policy import sensitive

    parent = (home if home is not None else Path.home()).expanduser().resolve()
    # A unique directory prevents deleting or overwriting unrelated files.
    directory = Path(tempfile.mkdtemp(prefix='BqPytest-', dir=str(parent))).resolve()
    try:
        if (not directory.is_dir() or sensitive(str(directory))
                or not _safe_path(directory, explicit_root=directory)):
            raise ValueError(f'Unsafe Windows pytest fixture root: {directory}')
        return directory
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def terminate_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # Windows process-tree termination is important for subprocess-backed
        # tests, so hanging node/python child tasks cannot survive this gate.
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=12, check=False)
    else:
        process.kill()
    try:
        process.wait(timeout=6)
    except subprocess.TimeoutExpired:
        process.kill()


def run(*, command: list[str] | None = None, root: Path = ROOT,
        idle_timeout: float = INACTIVITY_TIMEOUT,
        total_timeout: float = TOTAL_TIMEOUT) -> int:
    release = root / 'release'
    release.mkdir(parents=True, exist_ok=True)
    log = release / 'python-tests.log'
    # Don't display failed cases from an earlier build after a successful run.
    (release / 'python-tests-failures.txt').unlink(missing_ok=True)
    last = release / 'python-tests-last-test.txt'
    last.write_text('pytest startup\n', encoding='utf-8')
    # pytest-timeout on Windows uses its watchdog thread to end a hung test.
    # The external supervisor below also handles tests blocking before hooks run.
    pytest_basetemp: Path | None = None
    if command is None:
        if importlib.util.find_spec('pytest_timeout') is None:
            message = ('pytest-timeout missing in build venv; install requirements-desktop.txt '
                       'again. Tests were NOT skipped.\n')
            log.write_text(message, encoding='utf-8')
            print('[ERROR] ' + message, flush=True)
            return 2
        try:
            pytest_basetemp = create_safe_pytest_basetemp()
        except (OSError, ValueError, RuntimeError) as exc:
            message = f'Unable to create isolated safe pytest fixture directory: {exc}\n'
            log.write_text(message, encoding='utf-8')
            print('[BARQ TEST SETUP FAILED] ' + message, flush=True)
            return 2
        # Keep the EXACT same tests/strict flags; no tests are skipped or xfailed.
        command = [sys.executable, '-u', '-m', 'pytest', '-v', '--tb=short', '-ra', '--maxfail=20',
                   '--durations=15', '--timeout=90', '--timeout-method=thread',
                   f'--basetemp={pytest_basetemp}',
                   '--junitxml=release/python-tests.xml']
        (release / 'python-tests-environment.txt').write_text(
            f'pytest_fixture_root={pytest_basetemp}\n'
            f'build_project_root={root.resolve()}\n'
            'scope=isolated user-home fixtures; all existing tests enabled\n',
            encoding='utf-8')
        print(f'[BARQ PYTEST FIXTURES] Safe isolated root: {pytest_basetemp}', flush=True)
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    # Surface Python/native extension crash stacks in the release log when possible.
    env['PYTHONFAULTHANDLER'] = '1'
    # User-supplied pytest options/plugins must never silently alter what the
    # strict BARQ release suite tests or inject foreign pytest plugins.
    env.pop('PYTEST_ADDOPTS', None)
    env.pop('PYTEST_PLUGINS', None)
    env['PYTHONNOUSERSITE'] = '1'
    # stderr and stdout merge for a single, chronological diagnostic stream.
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    proc = subprocess.Popen(command, cwd=str(root), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=0, env=env,
                            creationflags=creationflags)
    chunks: queue.Queue[bytes | None] = queue.Queue()

    def pump() -> None:
        assert proc.stdout is not None
        try:
            while True:
                data = os.read(proc.stdout.fileno(), 4096)
                if not data:
                    break
                chunks.put(data)
        finally:
            chunks.put(None)

    thread = threading.Thread(target=pump, name='barq-pytest-output', daemon=True)
    thread.start()
    started = last_output = time.monotonic()
    tail = ''
    finished_stream = False
    reason: str | None = None
    try:
        with log.open('wb') as file:
            while True:
                try:
                    chunk = chunks.get(timeout=0.4)
                except queue.Empty:
                    chunk = b''
                if chunk is None:
                    finished_stream = True
                elif chunk:
                    last_output = time.monotonic()
                    file.write(chunk)
                    file.flush()
                    # Print partial lines too: pytest -v prints the running test
                    # BEFORE reporting PASSED or FAILED, so users see progress.
                    output = getattr(sys.stdout, 'buffer', None)
                    if output is not None:
                        output.write(chunk)
                        output.flush()
                    else:
                        sys.stdout.write(chunk.decode('utf-8', 'replace'))
                        sys.stdout.flush()
                    tail = (tail + chunk.decode('utf-8', 'replace'))[-9000:]
                    names = TEST_NAME.findall(tail)
                    if names:
                        last.write_text(names[-1] + '\n', encoding='utf-8')
                now = time.monotonic()
                if now - started > total_timeout:
                    reason = f'Entire pytest suite exceeded {total_timeout:.0f}s'
                elif now - last_output > idle_timeout:
                    reason = f'No pytest output for {idle_timeout:.0f}s; possible hung test'
                if reason:
                    # Never count the gate as passed when a timeout occurs.
                    diagnostic = (f'\n[BARQ TEST TIMEOUT] {reason}.\n'
                                  f'Last active test: {last.read_text(encoding="utf-8").strip()}\n'
                                  f'Log: {log}\n')
                    file.write(diagnostic.encode('utf-8'))
                    file.flush()
                    # A timeout must have the same single-file diagnosis as a
                    # normal pytest failure, including the interrupted test.
                    (release / 'python-tests-failures.txt').write_text(
                        f'TIMEOUT: {reason}\nLast active test: '
                        f'{last.read_text(encoding="utf-8").strip()}\n',
                        encoding='utf-8')
                    print(diagnostic, flush=True)
                    terminate_tree(proc)
                    return 124
                if finished_stream and proc.poll() is not None:
                    break
            code = proc.wait(timeout=8)
    finally:
        if proc.poll() is None:
            terminate_tree(proc)
        thread.join(timeout=2)
        if pytest_basetemp is not None:
            shutil.rmtree(pytest_basetemp, ignore_errors=True)
    if code != 0:
        # Show all failures from this run; stopping at the very first failure
        # makes Windows users rebuild repeatedly to discover the next one.
        failed = list(dict.fromkeys(re.findall(r'^FAILED\s+(tests[\\/][^\s]+)',
                                               log.read_text(encoding='utf-8', errors='replace'),
                                               flags=re.MULTILINE)))
        summary = release / 'python-tests-failures.txt'
        if failed:
            summary.write_text('\n'.join(failed) + '\n', encoding='utf-8')
            print(f'\n[BARQ] {len(failed)} failure(s) detected in ONE build, listing all:', flush=True)
            for name in failed:
                print(' - ' + name, flush=True)
        else:
            summary.write_text(f'pytest exit={code} (see python-tests.log)\n', encoding='utf-8')
        print(f'\n[BARQ TESTS FAILED] exit={code}. Open: {log}', flush=True)
        print(f'Last test: {last.read_text(encoding="utf-8").strip()}', flush=True)
    else:
        print(f'\n[BARQ TESTS PASSED] Full suite. Log: {log}', flush=True)
    return code



# A single Windows pytest interpreter can pass EVERY test and still terminate
# abnormally while shutting down native DLLs / COM / background services.  The
# release gate must not interpret the printed pytest summary as process success.
# Running small, complete file groups in fresh interpreters avoids shared native
# module shutdown state.  All test files are executed on EVERY release build.
DEFAULT_SHARD_FILES = 12


def _pytest_test_argument(root: PurePath, test_file: PurePath) -> str:
    """Produce portable pytest CLI paths on both Windows and POSIX.

    Path.__str__ returns ``tests\\test_x.py`` on Windows, whereas the test
    gate's command consumers and regression fixtures require ``tests/test_x.py``.
    Pytest accepts forward-slash relative paths on Windows.  A single canonical
    representation is also used when checking that no module was omitted.
    """
    relative = test_file.relative_to(root)
    if not relative.parts or relative.parts[0] != 'tests':
        raise ValueError(f'Not a relative pytest test module: {test_file}')
    return relative.as_posix()


def test_file_shards(root: Path = ROOT, size: int = DEFAULT_SHARD_FILES,
                     files: list[Path] | None = None) -> list[list[Path]]:
    """Partition every test_*.py exactly once, deterministically, no skipping."""
    if size < 1:
        raise ValueError('A test shard must have at least one file')
    selected = (list(files) if files is not None
                else list((root / 'tests').rglob('test_*.py')))
    selected = sorted((Path(f).resolve() for f in selected), key=lambda f: str(f).casefold())
    if not selected or len(selected) != len(set(selected)):
        raise ValueError('No tests found, or duplicate test files in pytest shards')
    for file in selected:
        if not file.is_file() or not file.is_relative_to((root / 'tests').resolve()):
            raise ValueError(f'Test file outside tests directory: {file}')
    return [selected[offset:offset + size] for offset in range(0, len(selected), size)]


def _junit_counts(path: Path) -> tuple[ET.Element, dict[str, int]]:
    if not path.is_file():
        raise ValueError(f'pytest completed but produced no JUnit XML: {path}')
    tree = ET.parse(path)
    root_element = tree.getroot()
    suites = ([root_element] if root_element.tag == 'testsuite'
              else list(root_element.findall('testsuite')))
    if not suites:
        raise ValueError('JUnit XML has no <testsuite> nodes')
    counts = {field: sum(int(s.get(field, '0')) for s in suites)
              for field in ('tests', 'errors', 'failures', 'skipped')}
    if counts['tests'] == 0:
        raise ValueError('pytest shard contained zero tests')
    if counts['errors'] or counts['failures']:
        raise ValueError('pytest exit code 0 but its JUnit XML contains failures')
    # Return the real testcase nodes; never synthesize passing testcases.
    aggregate = ET.Element('testsuites')
    for suite in suites:
        aggregate.append(suite)
    return aggregate, counts


def _shard_failure_details(log_path: Path, junit_path: Path) -> tuple[list[str], str]:
    """Extract actionable pytest failures even when the subprocess exits 1.

    Use structured JUnit failure/error tags first (handles collection and
    fixture errors), then the textual pytest summary, then a short traceback.
    A nonzero subprocess is NEVER treated as success because of these hints.
    """
    cases: list[str] = []
    excerpts: list[str] = []
    if junit_path.is_file():
        try:
            tree = ET.parse(junit_path)
            for case in tree.getroot().iter('testcase'):
                for node in case:
                    if node.tag not in ('failure', 'error'):
                        continue
                    title = (f"{case.get('classname', '?')}::{case.get('name', '?')} "
                             f"({node.tag})")
                    if title not in cases:
                        cases.append(title)
                    body = (node.get('message') or node.text or '').strip()
                    if body:
                        excerpts.append(f"{title}: {body[:1600]}")
        except (OSError, ValueError, ET.ParseError):
            pass
    try:
        contents = log_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        contents = ''
    for line in contents.splitlines():
        trimmed = line.strip()
        if (trimmed.startswith('FAILED tests/') or
                trimmed.startswith('FAILED tests\\') or
                trimmed.startswith('ERROR tests/') or
                trimmed.startswith('ERROR tests\\')):
            title = trimmed.split(' - ', 1)[0]
            if title not in cases:
                cases.append(title[:330])
    if not excerpts and contents:
        # Keep the diagnostic part of pytest logs rather than only the
        # start banner and warnings. Bound excerpts to avoid huge reports.
        for heading in ('=== FAILURES ===', '=== ERRORS ===',
                        'ERROR collecting', 'INTERNALERROR>', 'Fatal Python error',
                        'Traceback (most recent call last):'):
            pos = contents.find(heading)
            if pos >= 0:
                excerpts.append(contents[pos:pos+3500])
                break
    if not excerpts and contents:
        excerpts.append(contents[-1800:])
    return cases[:100], '\n'.join(excerpts)[:5000]


def run_sharded_suite(*, root: Path = ROOT,
                      shard_size: int = DEFAULT_SHARD_FILES,
                      files: list[Path] | None = None,
                      require_timeout_plugin: bool = True) -> int:
    """The Windows release test gate: all tests, isolated Python interpreters.

    Stops and blocks the installer on a test failure, timeout, missing JUnit
    evidence OR abnormal Windows process exit (including 0xC000030F).  An
    abnormal exit is NEVER converted to pass, even if the pytest log shows
    '1479 passed'.  Stable, per-shard logs identify the failing group.
    """
    release = root / 'release'
    release.mkdir(parents=True, exist_ok=True)
    log = release / 'python-tests.log'
    combined_log = release / 'python-tests-combined.log'
    last = release / 'python-tests-last-test.txt'
    failures = release / 'python-tests-failures.txt'
    evidence = release / 'python-tests-shards.json'
    junit = release / 'python-tests.xml'
    shards_dir = release / 'python-test-shards'
    shards_dir.mkdir(parents=True, exist_ok=True)
    failures.unlink(missing_ok=True)
    junit.unlink(missing_ok=True)
    # This is an error report for the CURRENT build, not stale evidence.
    evidence.unlink(missing_ok=True)
    if require_timeout_plugin and importlib.util.find_spec('pytest_timeout') is None:
        message = 'pytest-timeout not installed; full release suite NOT run.\n'
        log.write_text(message, encoding='utf-8')
        failures.write_text(message, encoding='utf-8')
        print('[BARQ PYTEST SHARDS ERROR] ' + message, flush=True)
        return 2
    try:
        shards = test_file_shards(root, shard_size, files)
        basetemp = create_safe_pytest_basetemp()
    except (OSError, ValueError, RuntimeError) as exc:
        message = f'Unable to prepare isolated pytest shards: {exc}\n'
        log.write_text(message, encoding='utf-8')
        failures.write_text(message, encoding='utf-8')
        print('[BARQ PYTEST SHARDS ERROR] ' + message, flush=True)
        return 2
    records: list[dict] = []
    combined = ET.Element('testsuites')
    total_counts = dict.fromkeys(('tests', 'errors', 'failures', 'skipped'), 0)
    start = time.monotonic()
    outcome = 0
    # Do not stop the ENTIRE release suite at the first failed test module.
    # Each shard already has its own fresh interpreter, allowing the other
    # shards to run even after a native DLL crash in one interpreter.
    failed_shards: list[str] = []
    try:
        # Streamed logs from run() are accumulated WITHOUT losing evidence for
        # previous batches.  The runner's existing tests and safety checks remain.
        with combined_log.open('wb') as full_log:
            for index, group in enumerate(shards, start=1):
                remaining = TOTAL_TIMEOUT - (time.monotonic() - start)
                if remaining <= 0:
                    outcome = 124
                    failed_shards.append('Full isolated pytest suite exceeded total timeout')
                    break
                title = (f'\\n[BARQ PYTEST SHARD {index}/{len(shards)}] '
                         f'{len(group)} file(s), Python subprocess with fresh native state\\n')
                full_log.write(title.replace('\\n', '\n').encode('utf-8'))
                print(title.replace('\\n', '\n'), flush=True)
                shard_junit = shards_dir / f'shard-{index:03d}.xml'
                shard_log = shards_dir / f'shard-{index:03d}.log'
                shard_junit.unlink(missing_ok=True)
                # Keep all existing pytest assertions, including timeout and
                # maxfail flags.  Explicit test paths cover 100% of test files.
                relative_files = [_pytest_test_argument(root, f) for f in group]
                command = [sys.executable, '-X', 'faulthandler', '-u', '-m', 'pytest',
                           '-v', '--tb=short', '-ra', '--maxfail=20',
                           '--durations=15', '--timeout=90', '--timeout-method=thread',
                           f'--basetemp={basetemp / f"shard-{index:03d}"}',
                           f'--junitxml={shard_junit}', *relative_files]
                started = time.monotonic()
                # Every shard runs with a *fresh* BARQ user-state directory.
                # Tests should never consume or modify the developer's real
                # Computer Control approvals, history, cache or indexing state.
                # This isolation is for pytest only; production keeps its
                # normal LOCALAPPDATA path and explicit consent policies.
                state_dir = basetemp / f'state-shard-{index:03d}'
                state_dir.mkdir(parents=True, exist_ok=True)
                prior_state = os.environ.get('AI_ROUTER_DATA_DIR')
                os.environ['AI_ROUTER_DATA_DIR'] = str(state_dir)
                try:
                    code = run(command=command, root=root, idle_timeout=INACTIVITY_TIMEOUT,
                               total_timeout=min(remaining, TOTAL_TIMEOUT))
                finally:
                    if prior_state is None:
                        os.environ.pop('AI_ROUTER_DATA_DIR', None)
                    else:
                        os.environ['AI_ROUTER_DATA_DIR'] = prior_state
                shard_source = release / 'python-tests.log'
                if shard_source.exists():
                    shutil.copyfile(shard_source, shard_log)
                    full_log.write(shard_source.read_bytes())
                record = dict(shard=index, files=relative_files, exit_code=code,
                              duration_seconds=round(time.monotonic() - started, 2),
                              log=str(shard_log), junit=str(shard_junit))
                if code:
                    # Keep every failed shard in its own log. Never treat a
                    # native crash or an XML-less pytest exit as a pass.
                    if code == 124:
                        outcome = 124
                    elif outcome == 0:
                        outcome = 2 if code == 2 else 1
                    record['failure'] = ('native_or_process_exit'
                                         if code < 0 or code > 255 else 'pytest_error')
                    record['exit_hex'] = f'0x{code & 0xffffffff:08X}'
                    failed, traceback = _shard_failure_details(shard_log, shard_junit)
                    record['failed_tests'] = failed
                    record['diagnostic_excerpt'] = traceback[:3000]
                    description = (f'SHARD {index}/{len(shards)} failed: {code} '
                                   f'({record["exit_hex"]}), '
                                   f'type={record["failure"]}, log={shard_log}\n'
                                   + ('\n'.join(failed) if failed else
                                      'Nonzero exit without named FAILED tests')
                                   + ('\n' + traceback[:3000] if traceback else
                                      '\nNo log or JUnit diagnostics were captured'))
                    failed_shards.append(description)
                    records.append(record)
                    # CONTINUE after failure: don't force another expensive
                    # React/npm/build cycle just to find the next test failure.
                    continue
                try:
                    shard_xml, counts = _junit_counts(shard_junit)
                except (ValueError, ET.ParseError, OSError) as exc:
                    record['failure'] = f'Invalid pytest completion evidence: {exc}'
                    records.append(record)
                    failed_shards.append(
                        f'SHARD {index}/{len(shards)} JUnit invalid: {exc}\n'
                        f'log={shard_log}')
                    outcome = outcome or 2
                    continue
                for suite in shard_xml:
                    combined.append(suite)
                for key, count in counts.items():
                    total_counts[key] += count
                record['counts'] = counts
                records.append(record)
            if failed_shards:
                report = ('BARQ Python test failures across ALL independent shards:\n'
                          + '\n\n'.join(failed_shards) + '\n')
                failures.write_text(report, encoding='utf-8')
                full_log.write(report.encode('utf-8', errors='replace'))
                print(report, flush=True)
            if outcome == 0:
                # Guard against a partial shard schedule being called success.
                tested = [name for r in records for name in r['files']]
                planned = [_pytest_test_argument(root, f) for g in shards for f in g]
                if tested != planned or len(records) != len(shards):
                    failures.write_text('Test coverage mismatch: not all shards executed\n', encoding='utf-8')
                    outcome = 2
                else:
                    combined.set('tests', str(total_counts['tests']))
                    combined.set('errors', str(total_counts['errors']))
                    combined.set('failures', str(total_counts['failures']))
                    combined.set('skipped', str(total_counts['skipped']))
                    ET.ElementTree(combined).write(junit, encoding='utf-8', xml_declaration=True)
                    message = (f'[BARQ PYTEST SHARDS PASSED] {len(shards)} native-isolated '
                               f'processes, {len(planned)} test modules, '
                               f'{total_counts["tests"]} test cases, '
                               f'{total_counts["skipped"]} skipped by existing markers. '
                               'All subprocess exit codes 0, all JUnit verified.\n')
                    full_log.write(message.encode('utf-8'))
                    print(message, flush=True)
    finally:
        shutil.rmtree(basetemp, ignore_errors=True)
        # write report on crash too; do not claim test counts from partial runs
        evidence.write_text(json.dumps(dict(success=(outcome == 0),
            processed_shards=len(records), planned_shards=len(shards),
            counts=total_counts, shards=records), ensure_ascii=False, indent=2),
            encoding='utf-8')
        # Restore the combined log as the canonical build log after each shard
        # overwrote python-tests.log.  Never overwrite a failed-shard artifact.
        if combined_log.exists():
            shutil.copyfile(combined_log, log)
    if outcome:
        if not failures.exists():
            failures.write_text('Python isolated pytest suite failed\n', encoding='utf-8')
        print(f'[BARQ PYTEST SHARDS FAILED] Exit {outcome}; report={evidence}; '
              f'failed modules={failures}', flush=True)
    return outcome


def check_imports() -> int:
    """Verify the packaged build runner imports BARQ's actual source tree."""
    try:
        from services import device_index
        from computer_control.safety.policy import sensitive
        expected = (ROOT / 'services' / 'device_index.py').resolve()
        found = Path(device_index.__file__).resolve()
        if found != expected:
            raise RuntimeError(f'Imported wrong device index: {found}; expected {expected}')
        if not callable(sensitive):
            raise RuntimeError('BARQ sensitive-path policy unavailable')
    except Exception:
        import traceback
        traceback.print_exc()
        print('[BARQ PYTEST IMPORT] FAILED: could not load staged project services',
              file=sys.stderr, flush=True)
        return 2
    print(f'[BARQ PYTEST IMPORT] PASS; project={ROOT}; module={found}', flush=True)
    return 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--check-imports']:
        raise SystemExit(check_imports())
    if sys.argv[1:] == ['--monolithic-diagnostic']:
        raise SystemExit(run())
    raise SystemExit(run_sharded_suite())
