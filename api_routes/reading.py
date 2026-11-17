"""Serve publisher-provided reading editions by catalogue ID."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

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
    with httpx.stream('GET', url, timeout=15, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=65536):
            pending.extend(chunk)
            if len(pending) > limit:
                raise ValueError('Reading edition exceeds the size limit')
    return bytes(pending)


@router.get('/books/{book_id}')
def edition(book_id: str):
    if book_id in HINDAWI:
        url = f'https://downloads.hindawi.org/books/{HINDAWI[book_id]}.pdf'
        pdf = True
    elif book_id in GUTENBERG:
        item = GUTENBERG[book_id]
        url = f'https://www.gutenberg.org/cache/epub/{item}/pg{item}.txt'
        pdf = False
    else:
        raise HTTPException(404, 'An in-app reading edition is unavailable')
    try:
        payload = download_edition(url, MAX_PDF if pdf else MAX_TEXT)
        if not payload or pdf and not payload.startswith(b'%PDF-'):
            raise ValueError('Invalid publisher response')
        if not pdf:
            payload.decode('utf-8-sig')
            if payload.lstrip().startswith(b'<'):
                raise ValueError('Expected a plain text edition')
    except (httpx.HTTPError, OSError, ValueError):
        raise HTTPException(502, 'Reading edition could not be loaded from its source') from None
    return Response(payload, media_type='application/pdf' if pdf else 'text/plain',
                    headers={'Cache-Control': 'private, max-age=86400', 'X-Content-Type-Options': 'nosniff'})
