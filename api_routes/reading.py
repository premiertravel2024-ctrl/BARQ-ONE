"""Serve publisher-provided reading editions by catalogue ID."""
from __future__ import annotations

import base64
import json
import os
import re
from hashlib import sha256
from threading import RLock
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
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


from api_routes.reading_drive import router as drive_router

router.include_router(drive_router)

from api_routes.reading_local_library import router as library_router
router.include_router(library_router)


MAX_COVER = 2 * 1024 * 1024
COVER_ORIGINAL = b'\x00'
COVER_LOCK = RLock()
COVER_HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}


def cover_path(book_id: str) -> Path:
    """Former path is retained as a read-only migration source."""
    if not 1 <= len(book_id) <= 2048:
        raise HTTPException(400, 'Invalid book identifier')
    return data_dir() / 'reading' / 'covers' / sha256(book_id.encode()).hexdigest()


def _load_legacy_cover(db, digest: str):
    """Import old AppData book covers into the user's G: SQLite database.

    Legacy files remain intact for recovery. A custom/hidden/restored row already
    present in SQLite is never replaced by an older AppData file.
    """
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        return
    if db.execute('SELECT 1 FROM cover_overrides WHERE id=?', (digest,)).fetchone():
        return
    legacy = data_dir() / 'reading' / 'covers' / digest
    try:
        with legacy.open('rb') as source:
            raw = source.read(MAX_COVER + 1)
        at = legacy.stat().st_mtime_ns // 1_000_000
    except (FileNotFoundError, PermissionError):
        return
    if len(raw) > MAX_COVER or (raw not in (b'', COVER_ORIGINAL) and not (
        raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9')
    )):
        return
    db.execute('INSERT OR IGNORE INTO cover_overrides(id,image,modified_ms) VALUES(?,?,?)',
               (digest, raw, at))


def _migrate_legacy_covers(db):
    directory = data_dir() / 'reading' / 'covers'
    for path in directory.glob('*'):
        if re.fullmatch(r'[a-f0-9]{64}', path.name) and path.is_file():
            _load_legacy_cover(db, path.name)


def _cover_row(db, digest: str):
    _load_legacy_cover(db, digest)
    return db.execute('SELECT image,modified_ms FROM cover_overrides WHERE id=?', (digest,)).fetchone()


@router.get('/covers/state/{book_id:path}')
def cover_state(book_id: str):
    from api_routes.reading_local_library import database, LOCK
    digest = cover_path(book_id).name
    with COVER_LOCK, LOCK, database() as db:
        row = _cover_row(db, digest)
        if row is None:
            return {'state': 'original'}
        raw = bytes(row['image'])
        return {'state': 'original' if raw == COVER_ORIGINAL else 'custom' if raw else 'hidden'}


@router.get('/covers/image/{book_id:path}')
def cover_image(book_id: str):
    from api_routes.reading_local_library import database, LOCK
    digest = cover_path(book_id).name
    with COVER_LOCK, LOCK, database() as db:
        row = _cover_row(db, digest)
        data = bytes(row['image']) if row is not None else b''
    if not data or data == COVER_ORIGINAL or len(data) > MAX_COVER:
        raise HTTPException(404, 'No custom cover')
    return Response(data, media_type='image/jpeg', headers=COVER_HEADERS)


@router.put('/covers/image/{book_id:path}')
async def set_cover(book_id: str, request: Request):
    path = cover_path(book_id)
    if request.headers.get('content-type') != 'image/jpeg':
        raise HTTPException(415, 'Expected a JPEG cover')
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_COVER:
            raise HTTPException(413, 'Cover is too large')
    if not data.startswith(b'\xff\xd8\xff') or not data.endswith(b'\xff\xd9'):
        raise HTTPException(422, 'Invalid JPEG cover')
    await run_in_threadpool(write_cover, path, data)
    return {'state': 'custom'}


def write_cover(path: Path, data: bytes | bytearray, *, modified_ms: int | None = None):
    """Atomically persist cover bytes in barq_library.sqlite3, not AppData."""
    from api_routes.reading_local_library import database, LOCK
    digest = path.name
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise ValueError('Invalid cover digest')
    payload = bytes(data)
    if len(payload) > MAX_COVER:
        raise ValueError('Cover is too large')
    if payload not in (b'', COVER_ORIGINAL) and not (
        payload.startswith(b'\xff\xd8\xff') and payload.endswith(b'\xff\xd9')
    ):
        raise ValueError('Invalid cover image')
    now = modified_ms if modified_ms is not None else __import__('time').time_ns() // 1_000_000
    with COVER_LOCK, LOCK, database() as db:
        db.execute("""INSERT INTO cover_overrides(id,image,modified_ms) VALUES(?,?,?)
            ON CONFLICT(id) DO UPDATE SET image=excluded.image, modified_ms=excluded.modified_ms""",
                   (digest, payload, now))


@router.post('/covers/hide/{book_id:path}')
def hide_cover(book_id: str):
    write_cover(cover_path(book_id), b'')
    return {'state': 'hidden'}


@router.delete('/covers/image/{book_id:path}')
def restore_cover(book_id: str):
    write_cover(cover_path(book_id), COVER_ORIGINAL)
    return {'state': 'original'}


def read_cover_sync(path: Path):
    from api_routes.reading_local_library import database, LOCK
    with COVER_LOCK, LOCK, database() as db:
        row = _cover_row(db, path.name)
    if row is None:
        return None
    data = bytes(row['image'])
    return {'at': int(row['modified_ms']),
            'value': None if data == COVER_ORIGINAL else base64.b64encode(data).decode('ascii')}


def cover_sync_snapshot():
    from api_routes.reading_local_library import database, LOCK
    with COVER_LOCK, LOCK, database() as db:
        _migrate_legacy_covers(db)
        entries = db.execute('SELECT id,image,modified_ms FROM cover_overrides').fetchall()
        return {
            'cover:' + row['id']: {
                'at': int(row['modified_ms']),
                'value': None if bytes(row['image']) == COVER_ORIGINAL else
                         base64.b64encode(bytes(row['image'])).decode('ascii')
            }
            for row in entries
        }


def apply_cover_sync(records, *, authoritative=False, expected=None):
    """Fill missing slots only; never discard or overwrite a local override.

    Last version fixed the 45-second sync deleting images. The SQLite migration
    preserves that non-destructive policy including explicit hide/restore markers.
    """
    from api_routes.reading_local_library import database, LOCK
    changed = False
    with COVER_LOCK, LOCK, database() as db:
        _migrate_legacy_covers(db)
        for key, entry in records.items():
            if not re.fullmatch(r'cover:[a-f0-9]{64}', key):
                continue
            if not isinstance(entry, dict) or type(entry.get('at')) is not int or 'value' not in entry:
                continue
            if not 0 <= entry['at'] <= 4_102_444_800_000:
                continue
            value = entry['value']
            try:
                if value is not None and (not isinstance(value, str) or len(value) > (MAX_COVER + 2) // 3 * 4):
                    continue
                data = COVER_ORIGINAL if value is None else base64.b64decode(value, validate=True)
                if len(data) > MAX_COVER:
                    continue
                if value is not None and data and not (
                    data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')
                ):
                    continue
            except (TypeError, ValueError):
                continue
            digest = key[6:]
            if db.execute('SELECT 1 FROM cover_overrides WHERE id=?', (digest,)).fetchone():
                continue
            if expected is not None and expected.get(key) is not None:
                continue
            db.execute('INSERT OR IGNORE INTO cover_overrides(id,image,modified_ms) VALUES(?,?,?)',
                       (digest, data, entry['at']))
            changed = True
    return changed
