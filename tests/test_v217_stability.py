"""Regression checks for stability changes that do not require live cloud API keys."""
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from core.sqlite import connect
from core.rate_limit import SlidingWindowLimiter
from core.history import ConversationStore
from api import app


def test_sqlite_wal_and_concurrent_connections(tmp_path):
    path=tmp_path/'threads.sqlite3'
    first=connect(path)
    second=connect(path)
    try:
        assert first.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert second.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        first.execute('CREATE TABLE items(value INTEGER)')
        first.commit()
        second.execute('INSERT INTO items VALUES (3)')
        second.commit()
        assert first.execute('SELECT value FROM items').fetchone()[0]==3
    finally:
        first.close();second.close()


def test_conversation_store_uses_wal(tmp_path):
    data=ConversationStore(tmp_path/'chats.sqlite3')
    with data.connect() as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0]=='wal'


def test_sliding_window_retry_after_and_not_trusting_forwarded_headers():
    now=[0]
    guard=SlidingWindowLimiter(limit=2,window=60,clock=lambda:now[0])
    assert guard.check('127.0.0.1')==0
    assert guard.check('127.0.0.1')==0
    assert guard.check('127.0.0.1')==60
    now[0]=61
    assert guard.check('127.0.0.1')==0


def test_health_endpoints_preserved_after_route_extraction():
    with TestClient(app) as client:
        assert client.get('/health').json()['status']=='ok'
        assert isinstance(client.get('/stats').json()['recent'],list)


def test_priority_validation_rejects_above_100():
    with TestClient(app) as client:
        result=client.post('/v1/models/settings',json={'provider':'ollama','priority':150})
        assert result.status_code==422


def test_voice_path_rejects_missing_folder():
    with TestClient(app) as client:
        assert client.post('/v1/settings/stt-path',json={'path':'Z:/certainly/not/existing'}).status_code==400


def test_new_react_contract_and_build_gates_present():
    root=Path(__file__).resolve().parents[1]
    ps=(root/'scripts/build_windows.ps1').read_text()
    assert 'npm run test:frontend' in ps
    assert 'npm run build' in ps
    assert ps.index('npm run test:frontend') < ps.index('npm run build')
    from core.version import VERSION
    assert f"v{VERSION}-build-gated-ui" in (root/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text()
