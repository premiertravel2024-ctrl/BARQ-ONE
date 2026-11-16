"""Bounded, deterministic Windows SQLite cleanup probe for BARQ release tests.

Do not start the real HTTP server here: the packaged-executable self-test
covers that separately after PyInstaller. This checks actual DB handle lifetime
in a temporary state directory and simulates Windows file-sharing semantics
on other operating systems. No user files or microphone access.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(report_path: str, *, inject_leak: bool = False) -> int:
    import desktop
    from brain.state import TaskStore
    from core.history import ConversationStore
    from core import sqlite as storage

    native_connect = sqlite3.connect
    native_tempdir = tempfile.TemporaryDirectory
    opened: list[tuple[Path, sqlite3.Connection]] = []
    tempdirs = []

    def tracked_connect(database, *args, **kwargs):
        # Keep strong references so GC cannot hide a leaked Windows handle.
        db = native_connect(database, *args, **kwargs)
        if str(database) != ':memory:' and not str(database).startswith('file:'):
            opened.append((Path(database).resolve(), db))
        return db

    class WindowsStrictTempdir(native_tempdir):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            tempdirs.append(self)

        def cleanup(self):
            root = Path(self.name).resolve()
            for path, db in opened:
                if not path.is_relative_to(root):
                    continue
                try:
                    db.execute('SELECT 1')
                except sqlite3.ProgrammingError as exc:
                    if 'closed' not in str(exc).lower():
                        raise
                    continue
                raise PermissionError(32, 'Simulated WinError 32: open SQLite handle', str(path))
            return super().cleanup()

    def database_health():
        state_root = Path(os.environ['AI_ROUTER_DATA_DIR'])
        tasks = TaskStore(state_root / 'tasks.sqlite3')
        task = tasks.begin('self-test', 'verify', 'sqlite lifecycle', str(state_root), 'probe')
        tasks.event(task['id'], 'verify', 'database closed')
        assert tasks.latest('self-test')['events'][0]['label'] == 'database closed'
        history = ConversationStore(state_root / 'history.sqlite3')
        history.put('chat', 'healthy', [])
        assert history.get('chat')['title'] == 'healthy'
        if inject_leak:
            # A deliberate leaked handle must block success on all platforms.
            storage.connect(state_root / 'unclosed.sqlite3').execute('CREATE TABLE leaked(x INTEGER)')
        return {'status': 'ok', 'sqlite_transactions_verified': True}

    sqlite3.connect = tracked_connect
    tempfile.TemporaryDirectory = WindowsStrictTempdir
    desktop.bundled_health_check = database_health
    try:
        code = desktop.write_self_test_report(report_path)
        data = json.loads(Path(report_path).read_text(encoding='utf-8'))
        if inject_leak:
            assert code == 1, data
            assert data.get('phase') == 'cleanup' and data.get('exception') == 'PermissionError', data
        else:
            assert code == 0 and data['status'] == 'ok' and data['cleanup_completed'], data
            assert opened, 'The probe did not exercise any SQLite file-backed connections'
            assert not any(Path(d.name).exists() for d in tempdirs), 'Temp directories were not deleted'
        return 0
    finally:
        sqlite3.connect = native_connect
        tempfile.TemporaryDirectory = native_tempdir
        for _, db in opened:
            try: db.close()
            except sqlite3.ProgrammingError: pass
        for directory in tempdirs:
            # If leak case failed cleanup, release the handles, then remove it.
            native_tempdir.cleanup(directory)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Usage: probe_sqlite_cleanup.py REPORT.json [--inject-leak]')
    raise SystemExit(run(sys.argv[1], inject_leak='--inject-leak' in sys.argv[2:]))
