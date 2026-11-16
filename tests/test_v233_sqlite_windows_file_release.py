"""Regression: Windows must be able to remove short-lived SQLite index files.

The sqlite3.Connection context manager commits/rolls back; it does NOT close
an open connection. Keep references alive deliberately to detect this trap even
on Linux (which otherwise allows unlinking open files).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Event

import pytest

from services import content_index, device_index


class TrackedConnection(sqlite3.Connection):
    close_called = False

    def close(self):
        self.close_called = True
        super().close()


def _watch_connections(monkeypatch):
    actual_connect = sqlite3.connect
    opened: list[TrackedConnection] = []

    def connect(*args, **kwargs):
        kwargs['factory'] = TrackedConnection
        db = actual_connect(*args, **kwargs)
        opened.append(db)
        return db

    monkeypatch.setattr(sqlite3, 'connect', connect)
    return opened


def test_scanning_search_and_content_index_explicitly_close_every_connection(tmp_path, monkeypatch):
    opened = _watch_connections(monkeypatch)
    root = tmp_path / 'allowed'
    root.mkdir()
    (root / 'important_note.txt').write_text('marmosetorchid', encoding='utf-8')
    movie = root / 'Movie.2160p.mkv'
    movie.write_bytes(b'x' * 2_100_000)
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setattr(device_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(content_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(device_index, '_everything_search', lambda *a, **kw: None)
    device_index._cancel.clear()
    content_index._cancel.clear()
    try:
        device_index.configure(enabled=True, content_enabled=True)
        assert device_index._scan([root], Event())['entries'] == 2
        assert device_index.search('important_note', allowed_folders=[str(root)])['results']
        assert device_index.browse_movies(allowed_folders=[str(root)])['movies']
        content_index._run([str(root)])
        assert content_index.search('marmosetorchid', [str(root)])['results']
    finally:
        device_index.configure(enabled=False)
    # Every tracked object stays referenced here: GC cannot hide a missing close.
    assert len(opened) >= 6
    assert all(db.close_called for db in opened), [
        i for i, db in enumerate(opened) if not db.close_called
    ]
    # A file whose connection has been closed should be free for Windows cleanup.
    metadata = state / 'device_index.sqlite3'
    target = state / 'moved.sqlite3'
    metadata.replace(target)
    target.replace(metadata)


def test_failed_database_initialization_releases_file_handle(tmp_path, monkeypatch):
    opened = _watch_connections(monkeypatch)
    state = tmp_path / 'state'
    state.mkdir()
    monkeypatch.setattr(device_index, 'state_file', lambda name: state / name)
    monkeypatch.setattr(content_index, 'state_file', lambda name: state / name)
    original_execute = TrackedConnection.execute

    def broken_metadata(self, sql, *args, **kwargs):
        if str(sql).startswith('PRAGMA journal_mode'):
            raise sqlite3.OperationalError('simulate sqlite initialization failure')
        return original_execute(self, sql, *args, **kwargs)

    monkeypatch.setattr(TrackedConnection, 'execute', broken_metadata)
    with pytest.raises(sqlite3.OperationalError, match='initialization failure'):
        device_index._connect()
    assert opened[-1].close_called

    def broken_content(self, sql, *args, **kwargs):
        if str(sql).startswith('CREATE VIRTUAL TABLE'):
            raise sqlite3.OperationalError('simulate FTS initialization failure')
        return original_execute(self, sql, *args, **kwargs)

    monkeypatch.setattr(TrackedConnection, 'execute', broken_content)
    with pytest.raises(sqlite3.OperationalError, match='FTS initialization failure'):
        content_index._db()
    assert opened[-1].close_called
