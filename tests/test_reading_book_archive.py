"""PDF bytes must be mirrored beside SQLite, deduplicated and readable offline."""
from hashlib import md5, sha256
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading, reading_drive, reading_local_library
from services import reading_book_archive as archive

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
BOOK1, BOOK2 = "ABCDEFGHIJKLMNOP", "qrstuvwxyzABCDEF"


class FakePdfResponse:
    status_code = 200
    def __init__(self, content: bytes):
        self.content = content
        self.headers = {"content-length": str(len(content))}
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return None
    def iter_bytes(self, chunk_size=65536):
        yield self.content[:9]
        yield self.content[9:]


def configure(tmp_path, monkeypatch, payloads=None):
    monkeypatch.setattr(reading_local_library, "db_path", lambda: tmp_path / "barq_library.sqlite3")
    archive._worker = None
    archive._state.update(processed=0, downloaded=0, failed=0, error="")
    payloads = payloads or {BOOK1:PDF,BOOK2:PDF}
    reading_drive.items.clear()
    monkeypatch.setattr(reading_drive, "remembered", lambda: {"folder":"owner-folder"})
    monkeypatch.setattr(reading_drive, "auth", lambda: {"Authorization":"Bearer owner"})
    def catalogue():
        reading_drive.items.clear()
        for book in payloads:
            reading_drive.items[book] = "application/pdf"
        return {"books":[{"id":book, "title":book, "group":"",
                          "md5":md5(value).hexdigest(), "cover":None}
                         for book,value in payloads.items()]}
    monkeypatch.setattr(reading_drive, "catalogue", catalogue)
    requests=[]
    def stream(method,url,params=None,headers=None,timeout=None):
        file_id=url.rsplit("/",1)[-1]
        requests.append(file_id)
        assert headers["Authorization"] == "Bearer owner"
        return FakePdfResponse(payloads[file_id])
    monkeypatch.setattr(archive.httpx, "stream", stream)
    app = FastAPI()
    app.include_router(reading.router)
    return TestClient(app), requests


def completed():
    assert archive._worker is not None
    archive._worker.join(timeout=6)
    assert not archive._worker.is_alive(), "Background archiving must finish promptly"


def test_actual_books_survive_restart_and_drive_disconnection(tmp_path,monkeypatch):
    api, requests = configure(tmp_path,monkeypatch)
    assert api.post("/v1/reading/library/refresh").status_code == 200
    assert api.post("/v1/reading/library/archive/start").status_code == 200
    completed()
    status=api.get("/v1/reading/library/archive/status").json()
    assert status["archived"]==2 and status["total"]==2
    assert status["failed"]==0
    assert set(requests)=={BOOK1,BOOK2}
    pdfs=list((tmp_path/"books").glob("*.pdf"))
    assert len(pdfs)==1, "Identical PDFs must share one content-addressed local copy"
    assert pdfs[0].read_bytes()==PDF
    assert pdfs[0].name==sha256(PDF).hexdigest()+".pdf"
    # The manifest and PDF bytes persist in a newly opened SQLite connection.
    from sqlite3 import connect
    with connect(tmp_path/"barq_library.sqlite3") as con:
        assert con.execute("SELECT COUNT(*) FROM book_archives").fetchone()[0]==2
        assert con.execute("PRAGMA quick_check(1)").fetchone()[0]=="ok"
    reading_drive.items.clear()
    monkeypatch.setattr(reading_drive,"remembered",lambda:None)
    monkeypatch.setattr(reading_drive,"auth",lambda: (_ for _ in ()).throw(RuntimeError("Drive offline")))
    old_count=len(requests)
    assert api.get("/v1/reading/drive/media/"+BOOK1).content==PDF
    assert api.get("/v1/reading/drive/media/"+BOOK2).content==PDF
    assert len(requests)==old_count, "Offline reader must not request Google after backup"
    ranged=api.get("/v1/reading/drive/media/"+BOOK1,headers={"Range":"bytes=0-6"})
    assert ranged.status_code==206
    assert ranged.content==PDF[:7]


def test_archive_does_not_trust_corrupted_files_and_never_overwrites_owner_original(tmp_path,monkeypatch):
    api,_=configure(tmp_path,monkeypatch,{BOOK1:PDF})
    assert api.post("/v1/reading/library/refresh").status_code==200
    api.post("/v1/reading/library/archive/start")
    completed()
    pdf=next((tmp_path/"books").glob("*.pdf"))
    pdf.write_bytes(b"not-a-pdf")
    # Invalid local data is never sent to PDF.js; system falls back to Drive.
    assert archive.archived_pdf(BOOK1) is None
    # The owner's Drive media remains unmodified, and the next backup repairs local bytes.
    api.post("/v1/reading/library/archive/start")
    completed()
    assert pdf.read_bytes()==PDF
    assert api.get("/v1/reading/drive/media/"+BOOK1).content==PDF


def test_archive_pause_keeps_saved_pdf_and_disables_future_auto_sync(tmp_path,monkeypatch):
    api,_=configure(tmp_path,monkeypatch,{BOOK1:PDF})
    api.post("/v1/reading/library/refresh")
    api.post("/v1/reading/library/archive/start")
    completed()
    status=api.post("/v1/reading/library/archive/stop").json()
    assert status["enabled"] is False
    assert api.post("/v1/reading/library/archive/resume").json()["enabled"] is False
    assert api.get("/v1/reading/drive/media/"+BOOK1).content==PDF
    assert next((tmp_path/"books").glob("*.pdf")).exists()
