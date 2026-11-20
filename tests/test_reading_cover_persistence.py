"""Regression: Google Drive sync must not erase an owner cover after 45 seconds."""
from __future__ import annotations

import base64
from hashlib import sha256

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading


IMAGE = b'\xff\xd8\xffowner-jpeg\xff\xd9'
REMOTE_IMAGE = b'\xff\xd8\xffother-device-jpeg\xff\xd9'


def client(tmp_path, monkeypatch):
    monkeypatch.setattr(reading, "data_dir", lambda: tmp_path)
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
