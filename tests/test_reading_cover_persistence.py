"""Regression: Google Drive sync must not erase an owner cover after 45 seconds."""
from __future__ import annotations

import base64
import sqlite3
from hashlib import sha256

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading, reading_local_library


IMAGE = b'\xff\xd8\xffowner-jpeg\xff\xd9'
REMOTE_IMAGE = b'\xff\xd8\xffother-device-jpeg\xff\xd9'


def client(tmp_path, monkeypatch):
    monkeypatch.setattr(reading, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(reading_local_library, "db_path", lambda: tmp_path / "barq_library.sqlite3")
    app = FastAPI()
    app.include_router(reading.router)
    return TestClient(app)


def slot(book_id: str) -> str:
    return "cover:" + sha256(book_id.encode()).hexdigest()


def remote_entry(data=REMOTE_IMAGE, at=2_000_000_000_000):
    return {"at": at, "value": base64.b64encode(data).decode("ascii")}


def test_new_uploaded_cover_survives_authoritative_sync_and_newer_remote(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    book = "library-series:my-stories"
    route = "/v1/reading/covers/image/" + book
    state = "/v1/reading/covers/state/" + book
    assert api.put(route, content=IMAGE, headers={"Content-Type": "image/jpeg"}).json() == {"state": "custom"}
    before = reading.cover_sync_snapshot()
    assert api.get(route).content == IMAGE

    # This is the exact old bug: a primary device does not include our cover.
    assert reading.apply_cover_sync({}, authoritative=True, expected=before) is False
    assert api.get(state).json()["state"] == "custom"
    assert api.get(route).content == IMAGE

    # Even a primary device with a conflicting newer image cannot undo a local edit.
    incoming = {slot(book): remote_entry()}
    assert reading.apply_cover_sync(incoming, authoritative=True, expected=before) is False
    assert api.get(route).content == IMAGE
    assert reading.cover_sync_snapshot()[slot(book)]["value"] == base64.b64encode(IMAGE).decode()


def test_local_explicit_restore_and_hide_survive_the_next_sync(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    for book, operation in [("book-hidden", "hide"), ("book-original", "restore")]:
        image = "/v1/reading/covers/image/" + book
        assert api.put(image, content=IMAGE, headers={"Content-Type": "image/jpeg"}).status_code == 200
        if operation == "hide":
            assert api.post("/v1/reading/covers/hide/" + book).json()["state"] == "hidden"
        else:
            assert api.delete(image).json()["state"] == "original"
        existing = reading.cover_sync_snapshot()
        assert reading.apply_cover_sync({slot(book): remote_entry()}, authoritative=True, expected=existing) is False
        assert api.get("/v1/reading/covers/state/" + book).json()["state"] == (
            "hidden" if operation == "hide" else "original"
        )
        assert api.get(image).status_code == 404


def test_remote_cover_initializes_only_a_missing_slot(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    book = "google:abcdefghijklmnopqrstuvwxyz"
    record = {slot(book): remote_entry()}
    assert reading.apply_cover_sync(record, authoritative=True, expected={}) is True
    assert api.get("/v1/reading/covers/image/" + book).content == REMOTE_IMAGE
    assert reading.apply_cover_sync(record, authoritative=True, expected=reading.cover_sync_snapshot()) is False
    assert api.get("/v1/reading/covers/image/" + book).content == REMOTE_IMAGE


def test_in_flight_sync_does_not_undo_a_newer_upload(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    book = "local:new-file"
    old_snapshot = reading.cover_sync_snapshot()
    image = "/v1/reading/covers/image/" + book
    assert api.put(image, content=IMAGE, headers={"Content-Type": "image/jpeg"}).status_code == 200
    assert reading.apply_cover_sync({slot(book): remote_entry()}, expected=old_snapshot, authoritative=True) is False
    assert api.get(image).content == IMAGE



def test_cover_is_a_durable_sqlite_blob_not_a_disappearing_temp_file(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    name = 'library-series:all-your-books'
    url = '/v1/reading/covers/image/' + name
    assert api.put(url, content=IMAGE, headers={'Content-Type':'image/jpeg'}).status_code == 200
    dbpath = tmp_path / 'barq_library.sqlite3'
    assert dbpath.is_file()
    with sqlite3.connect(dbpath) as connection:
        stored = connection.execute('SELECT image FROM cover_overrides WHERE id=?',
                                    (slot(name)[6:],)).fetchone()
        assert stored is not None and bytes(stored[0]) == IMAGE
        assert connection.execute('PRAGMA quick_check(1)').fetchone()[0] == 'ok'
    assert not reading.cover_path(name).exists()
    # A new client and database connection must return the same image.
    fresh = client(tmp_path, monkeypatch)
    assert fresh.get(url).content == IMAGE
    stats = fresh.get('/v1/reading/library/status').json()
    assert stats['persistent'] and stats['custom_covers'] == 1
    assert stats['journal_mode'] == 'wal'


def test_old_appdata_cover_is_migrated_once_and_never_overwrites_new_sqlite(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    name = 'library-series:old-book'
    oldfile = reading.cover_path(name)
    oldfile.parent.mkdir(parents=True)
    oldfile.write_bytes(IMAGE)
    url = '/v1/reading/covers/image/' + name
    assert api.get(url).content == IMAGE
    with sqlite3.connect(tmp_path / 'barq_library.sqlite3') as connection:
        assert bytes(connection.execute('SELECT image FROM cover_overrides WHERE id=?',
                                        (slot(name)[6:],)).fetchone()[0]) == IMAGE
    assert api.put(url, content=REMOTE_IMAGE, headers={'Content-Type':'image/jpeg'}).status_code == 200
    # Even with the old file present, the DB row is authoritative.
    assert api.get(url).content == REMOTE_IMAGE
    oldfile.unlink()
    assert client(tmp_path, monkeypatch).get(url).content == REMOTE_IMAGE
