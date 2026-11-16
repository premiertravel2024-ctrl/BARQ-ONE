"""Fast Windows build preflight for consented Temp metadata/content indexing.

This is an integrity check, not a way to bypass pytest. Run before the full
Python test gate so a mismatch of the source or Windows Temp path is reported
immediately, while the normal full suite still blocks the installer on failure.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def verify() -> int:
    from services import device_index, content_index

    source = Path(device_index.__file__).resolve()
    expected = (ROOT / 'services' / 'device_index.py').resolve()
    if source != expected:
        raise RuntimeError(f'Wrong device_index module imported: {source}; expected: {expected}')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    # Do not change the user's saved policy or real indexes in a build preflight.
    with tempfile.TemporaryDirectory(prefix='barq-search-preflight-') as directory:
        base = Path(directory).resolve()
        allowed = base / 'Allowed'
        allowed.mkdir()
        (allowed / 'barq_test_note.txt').write_text('ravenquickcheck', encoding='utf-8')
        nested = allowed / 'nested' / 'AppData' / 'Local' / 'Temp'
        nested.mkdir(parents=True)
        (nested / 'secret.txt').write_text('hidden-data', encoding='utf-8')
        (allowed / '.ssh').mkdir()
        (allowed / '.ssh' / 'key.txt').write_text('hidden', encoding='utf-8')
        state = base / 'state'
        state.mkdir()
        orig_state_device = device_index.state_file
        orig_state_content = content_index.state_file
        orig_everything = device_index._everything_search
        try:
            device_index.state_file = lambda filename: state / filename
            content_index.state_file = lambda filename: state / filename
            device_index._everything_search = lambda *a, **kw: None
            device_index.configure(enabled=True, content_enabled=True)
            roots = device_index.scan_roots(device_index.settings(), [str(allowed)])
            if roots != [allowed]:
                raise AssertionError(f'Consented Temp root was rejected: {roots}')
            scan = device_index._scan(roots, Event())
            if scan['entries'] != 1:
                raise AssertionError(f'Temp scope scanned {scan["entries"]} files; expected 1')
            named = device_index.search('barq_test_note', allowed_folders=[str(allowed)])['results']
            if len(named) != 1 or named[0]['name'] != 'barq_test_note.txt':
                raise AssertionError('Temp filename search missing approved file')
            content_index._cancel.clear()
            content_index._run([str(allowed)])
            hits = content_index.search('ravenquickcheck', [str(allowed)])['results']
            if len(hits) != 1 or hits[0]['name'] != 'barq_test_note.txt':
                raise AssertionError('Temp content search missing approved file')
            if device_index._safe_path_in_roots(nested / 'secret.txt', roots):
                raise AssertionError('Nested AppData was not excluded')
            if device_index._safe_path_in_roots(allowed / '.ssh' / 'key.txt', roots):
                raise AssertionError('Sensitive directory was not excluded')
            # The parent of a random TempDirectory may itself still be the
            # explicitly selectable Windows Temp folder. Check a root *above*
            # AppData rather than falsely denying legitimate Temp scopes.
            indices = device_index._explicit_temp_indices(base)
            if indices:
                index = min(indices)
                broad = Path(*base.parts[:index])
                if device_index._safe_path_in_roots(allowed / 'barq_test_note.txt', [broad]):
                    raise AssertionError('Broad root unexpectedly inherited AppData exemption')
        finally:
            device_index.configure(enabled=False)
            device_index.state_file = orig_state_device
            content_index.state_file = orig_state_content
            device_index._everything_search = orig_everything
        # Python sqlite3.Connection.__exit__ only commits/rolls back; it does
        # not close the native database handle. Windows then refuses to remove
        # this TemporaryDirectory (WinError 32). Detect that exact regression
        # before context-manager cleanup so the failure is actionable.
        db_file = state / 'device_index.sqlite3'
        if db_file.exists():
            probe = state / 'device_index.sqlite3.closed-probe'
            try:
                db_file.replace(probe)
                probe.replace(db_file)
            except OSError as exc:
                raise RuntimeError(
                    f'Windows SQLite file handle is still open: {db_file}; '
                    'check explicit connection.close() in services/device_index.py'
                ) from exc
        print('[BARQ SQLITE HANDLES] PASS; temporary index database can be renamed', flush=True)
    print(f'[BARQ TEMP-SCOPE FIX] PASS; source={source}; SHA256={digest}', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(verify())
    except Exception as exc:
        print(f'[BARQ TEMP-SCOPE FIX] FAILED: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        raise
