"""Private owner-side SQLite library index. BARQ's desktop API must remain loopback-only.

The index stores book metadata, publication choices and series, NOT Google tokens.
Google OAuth stays in the existing keyring-backed reading_drive module.
New books are private until the owner publishes them in the isolated online gateway.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from pathlib import Path
from threading import RLock
import os
import re
import sqlite3
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.paths import data_dir

router = APIRouter(prefix='/library')
LOCK = RLock()
ID = re.compile(r'^[a-zA-Z0-9_-]{10,160}$')
SERIES_ID = re.compile(r'^[a-f0-9-]{36}$')


def db_path() -> Path:
    configured = os.environ.get('BARQ_READING_DB_DIR', '').strip()
    if configured:
        parent = Path(configured).expanduser()
    elif os.name == 'nt' and Path('G:/BARQ DATABASE').is_dir():
        parent = Path('G:/BARQ DATABASE')
    else:
        parent = data_dir() / 'reading'
    return parent / 'barq_library.sqlite3'


@contextmanager
def database():
    destination = db_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(destination), timeout=15)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS series (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_title TEXT NOT NULL,
                folder_name TEXT NOT NULL DEFAULT '',
                cover_id TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                published INTEGER NOT NULL DEFAULT 0,
                series_id TEXT REFERENCES series(id) ON DELETE SET NULL,
                issue_number INTEGER,
                position INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_books_series ON books(series_id,issue_number,position);
        ''')
        with db:
            yield db


class SeriesInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=500)


class EditBook(BaseModel):
    id: str
    title: str | None = Field(default=None, max_length=250)
    published: bool | None = None
    series_id: str | None = None
    issue_number: int | None = Field(default=None, ge=1, le=100000)
    position: int | None = Field(default=None, ge=0, le=100000)


def validate_id(value: str) -> None:
    if not ID.fullmatch(value):
        raise HTTPException(422, 'Invalid Google Drive file ID')


def snapshot(db):
    books = [dict(row) for row in db.execute(
        'SELECT id,title,folder_name,cover_id,active,published,series_id,issue_number,position '
        'FROM books ORDER BY position,issue_number,title')]
    series = [dict(row) for row in db.execute(
        'SELECT id,title,description,position FROM series ORDER BY position,title')]
    return {'books': books, 'series': series}


@router.get('/items')
def items():
    with LOCK, database() as db:
        return snapshot(db)


@router.get('/status')
def status():
    with LOCK, database() as db:
        count = db.execute('SELECT COUNT(*) FROM books WHERE active=1').fetchone()[0]
        return {'count': count, 'database': str(db_path())}


@router.post('/refresh')
def refresh():
    from api_routes import reading_drive
    catalogue = reading_drive.catalogue()
    books = catalogue.get('books', [])
    for book in books:
        validate_id(book['id'])
    with LOCK, database() as db:
        # A single transaction avoids a half-written catalogue if Google Drive fails.
        db.execute('UPDATE books SET active=0')
        for book in books:
            title = str(book['title'])[:250]
            folder = str(book.get('group', ''))[:300]
            cover_id = book.get('cover')
            if cover_id is not None:
                validate_id(cover_id)
            db.execute('''
                INSERT INTO books(id,title,source_title,folder_name,cover_id,active)
                VALUES(?,?,?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET
                  source_title=excluded.source_title,
                  folder_name=excluded.folder_name,
                  cover_id=excluded.cover_id,
                  active=1
            ''', (book['id'], title, title, folder, cover_id))
        return {'synced': len(books), 'database': str(db_path())}


@router.post('/series')
def add_series(info: SeriesInput):
    name = info.title.strip()
    if not name:
        raise HTTPException(422, 'Series name required')
    identifier = str(uuid.uuid4())
    with LOCK, database() as db:
        db.execute('INSERT INTO series(id,title,description) VALUES(?,?,?)',
                   (identifier, name, info.description))
    return {'id': identifier, 'title': name}


@router.post('/book')
def edit_book(info: EditBook):
    validate_id(info.id)
    if info.series_id is not None and not SERIES_ID.fullmatch(info.series_id):
        raise HTTPException(422, 'Invalid series ID')
    with LOCK, database() as db:
        row = db.execute('SELECT id FROM books WHERE id=? AND active=1', (info.id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Book not found')
        fields = info.model_fields_set
        if 'series_id' in fields and info.series_id is not None:
            exists = db.execute('SELECT id FROM series WHERE id=?', (info.series_id,)).fetchone()
            if exists is None:
                raise HTTPException(422, 'Series not found')
        updates = {}
        if 'title' in fields:
            if not info.title or not info.title.strip():
                raise HTTPException(422, 'Empty title')
            updates['title'] = info.title.strip()
        if 'published' in fields:
            updates['published'] = int(info.published)
        if 'series_id' in fields:
            updates['series_id'] = info.series_id
        if 'issue_number' in fields:
            updates['issue_number'] = info.issue_number
        if 'position' in fields:
            updates['position'] = info.position
        if updates:
            columns = ', '.join(key + '=?' for key in updates)
            db.execute('UPDATE books SET ' + columns + ' WHERE id=?',
                       (*updates.values(), info.id))
    return {'updated': True}


@router.delete('/series/{series_id}')
def delete_series(series_id: str):
    if not SERIES_ID.fullmatch(series_id):
        raise HTTPException(422, 'Invalid series ID')
    with LOCK, database() as db:
        db.execute('DELETE FROM series WHERE id=?', (series_id,))
    return {'deleted': True}
