import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading


def test_reading_uses_fixed_public_editions(monkeypatch, tmp_path):
    monkeypatch.setattr(reading, 'data_dir', lambda: tmp_path)
    seen = []

    def download(url, limit):
        seen.append((url, limit))
        return b'%PDF-1.4\n' if url.endswith('.pdf') else b'An authorized text edition'

    monkeypatch.setattr(reading, 'download_edition', download)
    app = FastAPI()
    app.include_router(reading.router)
    client = TestClient(app)

    response = client.get('/v1/reading/books/egy-zenab')
    assert response.headers['content-type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF-')
    text = client.get('/v1/reading/books/world-alice')
    assert text.headers['content-type'].startswith('text/plain')
    assert client.get('/v1/reading/books/paranormal').status_code == 404
    assert client.get('/v1/reading/books/unknown?url=http://localhost').status_code == 404
    assert seen == [
        ('https://downloads.hindawi.org/books/28493759.pdf', reading.MAX_PDF),
        ('https://www.gutenberg.org/cache/epub/11/pg11.txt', reading.MAX_TEXT),
    ]


def test_reader_rejects_a_publisher_error_page(monkeypatch, tmp_path):
    monkeypatch.setattr(reading, 'data_dir', lambda: tmp_path)
    monkeypatch.setattr(reading, 'download_edition', lambda *args: b'<html>Error</html>')
    app = FastAPI()
    app.include_router(reading.router)
    client = TestClient(app)
    assert client.get('/v1/reading/books/egy-zenab').status_code == 502
    assert client.get('/v1/reading/books/world-alice').status_code == 502


def test_jekyll_opens_offline_and_downloaded_pdfs_survive_an_outage(monkeypatch, tmp_path):
    monkeypatch.setattr(reading, 'data_dir', lambda: tmp_path)
    app = FastAPI()
    app.include_router(reading.router)
    client = TestClient(app)
    payload = b'%PDF-1.4\n'
    monkeypatch.setattr(reading, 'download_edition', lambda *args: payload)
    assert client.get('/v1/reading/books/egy-zenab').content == payload

    def unavailable(*args):
        raise httpx.ConnectError('Publisher unavailable')

    monkeypatch.setattr(reading, 'download_edition', unavailable)
    book = client.get('/v1/reading/books/world-jekyll')
    assert book.status_code == 200
    assert b'STORY OF THE DOOR' in book.content
    assert client.get('/v1/reading/books/egy-zenab').content == payload
    assert client.get('/v1/reading/books/egy-east').status_code == 502
