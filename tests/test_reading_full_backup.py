"""Disaster-recovery ZIP includes real book bytes as well as SQLite metadata."""
from hashlib import sha256
import sqlite3
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading, reading_local_library
from services import reading_full_backup

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
BOOK = "ABCDEFGHIJKLMNOP"


def make(tmp_path, monkeypatch, valid=True):
    monkeypatch.setattr(reading_local_library, "db_path", lambda: tmp_path / "barq_library.sqlite3")
    reading_full_backup._worker = None
    reading_full_backup._state.update(running=False, copied=0, total=0, file="", bytes=0, error="")
    digest = sha256(PDF).hexdigest()
    folder = tmp_path / "books"
    folder.mkdir(exist_ok=True)
    file = folder / f"{digest}.pdf"
    file.write_bytes(PDF if valid else b"bad contents")
    with reading_local_library.LOCK, reading_local_library.database() as db:
        db.execute("INSERT INTO books(id,title,source_title) VALUES(?,?,?)",
                   (BOOK, "أول رواية", "أول رواية"))
        db.execute("INSERT INTO cover_overrides(id,image,modified_ms) VALUES(?,?,?)",
                   ("a"*64,b"\xff\xd8\xffcover\xff\xd9",100))
        db.execute("INSERT INTO reader_state(key,value) VALUES(?,?)",
                   ("barq-reader:google:"+BOOK,'{"page":17,"marks":[17]}'))
        db.execute("INSERT INTO book_archives(file_id,digest,size,source_md5,stored_at) VALUES(?,?,?,?,?)",
                   (BOOK,digest,len(PDF),None,"2026-11-21T01:02:03+00:00"))
    app = FastAPI()
    app.include_router(reading.router)
    return TestClient(app), file


def finished():
    assert reading_full_backup._worker is not None
    reading_full_backup._worker.join(timeout=10)
    assert not reading_full_backup._worker.is_alive()


def test_complete_library_backup_restores_all_metadata_and_real_pdf_bytes(tmp_path, monkeypatch):
    api, _ = make(tmp_path,monkeypatch)
    assert api.post("/v1/reading/library/backup/full").status_code==200
    finished()
    status=api.get("/v1/reading/library/backup/full/status").json()
    assert not status["running"] and not status["error"]
    assert status["copied"]==1 and status["total"]==1
    import pathlib
    packed=pathlib.Path(status["file"])
    assert packed.is_file()
    with ZipFile(packed) as zip:
        assert zip.testzip() is None
        assert zip.read("books/"+sha256(PDF).hexdigest()+".pdf")==PDF
        import json
        assert json.loads(zip.read("manifest.json"))["format"]=="barq-library-complete-v1"
        snap=tmp_path/"verification.sqlite3"
        snap.write_bytes(zip.read("barq_library.sqlite3"))
    with sqlite3.connect(snap) as db:
        assert db.execute("PRAGMA quick_check(1)").fetchone()[0]=="ok"
        assert db.execute("SELECT title FROM books WHERE id=?",(BOOK,)).fetchone()[0]=="أول رواية"
        assert db.execute("SELECT value FROM reader_state").fetchone()[0]=='{"page":17,"marks":[17]}'
        assert db.execute("SELECT COUNT(*) FROM cover_overrides").fetchone()[0]==1


def test_damaged_book_prevents_a_misleading_complete_backup(tmp_path,monkeypatch):
    api,_=make(tmp_path,monkeypatch,valid=False)
    assert api.post("/v1/reading/library/backup/full").status_code==200
    finished()
    status=api.get("/v1/reading/library/backup/full/status").json()
    assert status["error"] and not status["file"]
    assert not list((tmp_path/"backups").glob("BARQ_FULL_LIBRARY*.zip"))
    assert not list((tmp_path/"backups").glob("*.part"))



def test_full_backup_never_claims_success_when_some_books_have_no_local_copy(tmp_path,monkeypatch):
    api, _=make(tmp_path,monkeypatch)
    with reading_local_library.LOCK, reading_local_library.database() as db:
        db.execute("INSERT INTO books(id,title,source_title) VALUES(?,?,?)",
                   ("qrstuvwxyzABCDEF","Book not yet downloaded","Book not yet downloaded"))
    assert api.post("/v1/reading/library/backup/full").status_code==200
    finished()
    status=api.get("/v1/reading/library/backup/full/status").json()
    assert status["error"] and "not copied offline yet" in status["error"]
    assert not status["file"]
