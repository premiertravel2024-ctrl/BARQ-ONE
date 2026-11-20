"""Owner-managed BARQ library regression tests; no real Google credentials required."""
import sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading_local_library


def client(tmp_path, monkeypatch):
    destination = tmp_path / 'barq_library.sqlite3'
    monkeypatch.setattr(reading_local_library, 'db_path', lambda: destination)
    app = FastAPI()
    app.include_router(reading_local_library.router)
    return TestClient(app), destination


def test_default_private_and_series_changes_survive_drive_resync(tmp_path, monkeypatch):
    test, db_path = client(tmp_path, monkeypatch)
    from api_routes import reading_drive

    listings = [[
        {'id':'abcdefghijklmnop', 'title':'01 - Episode', 'group':'Series A', 'cover':None},
        {'id':'qrstuvwxyzABCDEF', 'title':'02 - Episode', 'group':'Series A', 'cover':None},
    ]]
    monkeypatch.setattr(reading_drive, 'catalogue', lambda: {'books':listings[0]})
    assert test.post('/library/refresh').json()['synced'] == 2

    data = test.get('/library/items').json()
    assert len(data['books']) == 2
    assert all(book['published'] == 0 for book in data['books'])

    created = test.post('/library/series', json={'title':'Series A'}).json()
    assert created['title'] == 'Series A'
    save = test.post('/library/book', json={
        'id':'abcdefghijklmnop','series_id':created['id'],'issue_number':1,
        'position':1,'published':True,
    })
    assert save.status_code == 200

    # Source title changes do not override the owner's series mapping or publication.
    listings[0] = [
        {'id':'abcdefghijklmnop','title':'Episode renamed on Drive','group':'Series A','cover':None},
    ]
    assert test.post('/library/refresh').json()['synced'] == 1
    snapshot = test.get('/library/items').json()
    updated = next(book for book in snapshot['books'] if book['id'] == 'abcdefghijklmnop')
    removed = next(book for book in snapshot['books'] if book['id'] == 'qrstuvwxyzABCDEF')
    assert updated['title'] == '01 - Episode'
    assert updated['published'] == 1
    assert updated['series_id'] == created['id']
    assert updated['issue_number'] == 1
    assert removed['active'] == 0

    with sqlite3.connect(db_path) as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'


def test_invalid_edit_is_rejected_and_not_published(tmp_path, monkeypatch):
    test, _ = client(tmp_path, monkeypatch)
    assert test.post('/library/book', json={'id':'bad id','published':True}).status_code == 422
    assert test.post('/library/book', json={'id':'abcdefghijklmnop','published':True}).status_code == 404
    assert test.post('/library/series',json={'title':'  '}).status_code == 422
    assert test.delete('/library/series/not-a-uuid').status_code == 422


def test_local_database_location_can_be_configured(tmp_path, monkeypatch):
    monkeypatch.setenv('BARQ_READING_DB_DIR',str(tmp_path))
    assert reading_local_library.db_path() == tmp_path / 'barq_library.sqlite3'
