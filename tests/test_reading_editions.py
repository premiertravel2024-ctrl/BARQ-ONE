from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import reading


def test_reading_uses_fixed_public_editions(monkeypatch):
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


def test_reader_rejects_a_publisher_error_page(monkeypatch):
    monkeypatch.setattr(reading, 'download_edition', lambda *args: b'<html>Error</html>')
    app = FastAPI()
    app.include_router(reading.router)
    client = TestClient(app)
    assert client.get('/v1/reading/books/egy-zenab').status_code == 502
    assert client.get('/v1/reading/books/world-alice').status_code == 502
