"""Serve publisher-provided reading editions by catalogue ID."""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from core.paths import data_dir, resource

router = APIRouter(prefix='/v1/reading', tags=['reading'])
HINDAWI = {'egy-awda': 31425393, 'egy-palace': 84275792, 'egy-zenab': 28493759, 'egy-east': 74917046}
GUTENBERG = {
    'world-dracula': 345, 'world-frankenstein': 84, 'world-jekyll': 43,
    'world-alice': 11, 'world-monte-cristo': 1184, 'world-pride': 1342,
    'world-time': 35, 'world-sherlock': 1661,
}
MAX_PDF = 32 * 1024 * 1024
MAX_TEXT = 8 * 1024 * 1024


def download_edition(url: str, limit: int) -> bytes:
    pending = bytearray()
    with httpx.stream('GET', url, timeout=httpx.Timeout(10, connect=4), follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=65536):
            pending.extend(chunk)
            if len(pending) > limit:
                raise ValueError('Reading edition exceeds the size limit')
    return bytes(pending)


def validated(payload: bytes, pdf: bool) -> bytes:
    if not payload or pdf and not payload.startswith(b'%PDF-'):
        raise ValueError('Invalid publisher response')
    if not pdf:
        text = payload.decode('utf-8-sig').strip()
        if not text or text.startswith('<'):
            raise ValueError('Expected a plain text edition')
    return payload


def stored_edition(path: Path, limit: int, pdf: bool) -> bytes | None:
    try:
        with path.open('rb') as source:
            payload = source.read(limit + 1)
        if len(payload) <= limit:
            return validated(payload, pdf)
    except (OSError, ValueError):
        pass
    return None


def save_edition(path: Path, payload: bytes) -> None:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as target:
            temporary = Path(target.name)
            target.write(payload)
        temporary.replace(path)
    except OSError:
        pass  # Reading still works in a read-only installation.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


@router.get('/books/{book_id}')
def edition(book_id: str):
    if book_id in HINDAWI:
        urls = (f'https://downloads.hindawi.org/books/{HINDAWI[book_id]}.pdf',) * 2
        pdf = True
    elif book_id in GUTENBERG:
        item = GUTENBERG[book_id]
        urls = (f'https://www.gutenberg.org/cache/epub/{item}/pg{item}.txt',
                f'https://www.gutenberg.org/files/{item}/{item}-0.txt')
        pdf = False
    else:
        raise HTTPException(404, 'An in-app reading edition is unavailable')
    limit = MAX_PDF if pdf else MAX_TEXT
    payload = None
    if book_id == 'world-jekyll':
        payload = (stored_edition(resource('web', 'react', 'reading', '43.txt'), limit, pdf)
                   or stored_edition(resource('frontend', 'public', 'reading', '43.txt'), limit, pdf))
    if payload is None:
        try:
            cache = data_dir() / 'reading' / book_id
        except OSError:
            cache = None
        if cache is not None:
            payload = stored_edition(cache, limit, pdf)
        if payload is None:
            for url in urls:
                try:
                    payload = validated(download_edition(url, limit), pdf)
                except (httpx.HTTPError, OSError, ValueError):
                    continue
                if cache is not None:
                    save_edition(cache, payload)
                break
    if payload is None:
        raise HTTPException(502, 'Reading edition could not be loaded from its source')
    return Response(payload, media_type='application/pdf' if pdf else 'text/plain',
                    headers={'Cache-Control': 'private, max-age=86400', 'X-Content-Type-Options': 'nosniff'})
