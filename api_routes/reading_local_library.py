"""Owner-side BARQ ONE catalogue and automatic reading library organizer.

Uses local SQLite, never shares Google Drive credentials or files with online readers.
The isolated public Cloudflare library retains its own explicit publish permissions.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from pathlib import Path
from threading import RLock
from datetime import datetime, timezone
import os
import re
import sqlite3
import uuid
import shutil
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.paths import data_dir
from services.library_organizer import organize, normalized

router = APIRouter(prefix="/library")
LOCK = RLock()
ID = re.compile(r"^[a-zA-Z0-9_-]{10,160}$")
SERIES_ID = re.compile(r"^[a-f0-9-]{36}$")


# Choose a persistent destination once per process. A temporary G: disconnect
# must never silently switch BARQ to a second, apparently empty database.
_PINNED_DB_PATH: Path | None = None


def db_path() -> Path:
    configured = os.environ.get("BARQ_READING_DB_DIR", "").strip()
    if configured:
        return Path(configured).expanduser() / "barq_library.sqlite3"
    global _PINNED_DB_PATH
    if _PINNED_DB_PATH is None:
        preferred = Path("G:/BARQ DATABASE")
        parent = preferred if os.name == "nt" and preferred.is_dir() else data_dir() / "reading"
        _PINNED_DB_PATH = parent / "barq_library.sqlite3"
    return _PINNED_DB_PATH


def migrate_previous_database(destination: Path) -> None:
    """Copy an existing default Windows catalogue to G: exactly once.

    SQLite's online backup API captures WAL changes too; copying just the
    .sqlite3 file risks losing recently committed changes.
    """
    if destination.exists() or os.environ.get("BARQ_READING_DB_DIR"):
        return
    legacy = data_dir() / "reading" / "barq_library.sqlite3"
    if legacy == destination or not legacy.is_file():
        return
    with NamedTemporaryFile(dir=destination.parent, prefix=".barq-migration-", suffix=".sqlite3", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        with closing(sqlite3.connect(str(legacy), timeout=15)) as source, closing(sqlite3.connect(str(temporary))) as copied:
            source.backup(copied)
        # Exclusive migration runs under LOCK; never replace an existing G: catalogue.
        if not destination.exists():
            temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def schema(db):
    db.executescript("""
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
    """)
    series_columns = {row["name"] for row in db.execute("PRAGMA table_info(series)")}
    if "source_key" not in series_columns:
        db.execute("ALTER TABLE series ADD COLUMN source_key TEXT")
    if "genre" not in series_columns:
        db.execute("ALTER TABLE series ADD COLUMN genre TEXT NOT NULL DEFAULT ''")
    columns = {row["name"] for row in db.execute("PRAGMA table_info(books)")}
    additions = {
        "manual_series": "INTEGER NOT NULL DEFAULT 0",
        "manual_issue": "INTEGER NOT NULL DEFAULT 0",
        "manual_title": "INTEGER NOT NULL DEFAULT 0",
        "manual_position": "INTEGER NOT NULL DEFAULT 0",
        "hidden": "INTEGER NOT NULL DEFAULT 0",
        "review_reason": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in additions.items():
        if name not in columns:
            db.execute(f"ALTER TABLE books ADD COLUMN {name} {definition}")
            if name == "manual_series":
                # Pre-upgrade owner assignments must never be changed by indexing.
                db.execute("UPDATE books SET manual_series=1 WHERE series_id IS NOT NULL")
            if name == "manual_issue":
                db.execute("UPDATE books SET manual_issue=1 WHERE issue_number IS NOT NULL")
            if name == "manual_position":
                db.execute("UPDATE books SET manual_position=1 WHERE position<>0")
            if name == "manual_title":
                db.execute("UPDATE books SET manual_title=1 WHERE title<>source_title")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_series_source ON series(source_key)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_books_series ON books(series_id,issue_number,position)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_books_review ON books(active,review_reason)")
    # Images, hides and restores are durable metadata in the same user database.
    db.execute("""CREATE TABLE IF NOT EXISTS cover_overrides (
        id TEXT PRIMARY KEY,
        image BLOB NOT NULL,
        modified_ms INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS library_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")


@contextmanager
def database():
    destination = db_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    migrate_previous_database(destination)
    with closing(sqlite3.connect(str(destination), timeout=15)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        schema(db)
        with db:
            yield db
            if db.total_changes:
                db.execute("""INSERT INTO library_meta(key,value) VALUES('last_saved_at',?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"),))


def identifier(value: str) -> str:
    if not ID.fullmatch(value):
        raise HTTPException(422, "Invalid Drive file identifier")
    return value


def series_id(value: str) -> str:
    if not SERIES_ID.fullmatch(value):
        raise HTTPException(422, "Invalid series identifier")
    return value


def series_exists(db, value):
    if value is not None and not db.execute("SELECT 1 FROM series WHERE id=?", (series_id(value),)).fetchone():
        raise HTTPException(422, "Series does not exist")


def snapshot(db):
    books = [dict(row) for row in db.execute(
        "SELECT id,title,source_title,folder_name,cover_id,active,published,hidden,"
        "series_id,issue_number,position,review_reason,manual_series,manual_issue,"
        "manual_title,manual_position FROM books ORDER BY position,issue_number,title")]
    series = [dict(row) for row in db.execute(
        "SELECT id,title,description,genre,position,source_key FROM series ORDER BY position,title")]
    return {"books": books, "series": series}


class SeriesInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    genre: str = Field(default="", max_length=60)


class SeriesEdit(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    genre: str | None = Field(default=None, max_length=60)
    position: int | None = Field(default=None, ge=0, le=100000)


class EditBook(BaseModel):
    id: str
    title: str | None = Field(default=None, max_length=250)
    hidden: bool | None = None
    published: bool | None = None
    series_id: str | None = None
    issue_number: int | None = Field(default=None, ge=1, le=100000)
    position: int | None = Field(default=None, ge=0, le=100000)


class BulkEdit(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=400)
    series_id: str | None = None
    hidden: bool | None = None
    published: bool | None = None


class SeriesMerge(BaseModel):
    source: str
    target: str


class Reorder(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=400)


@router.get("/items")
def items():
    with LOCK, database() as db:
        return snapshot(db)


@router.get("/status")
def status():
    with LOCK, database() as db:
        active = db.execute("SELECT COUNT(*) FROM books WHERE active=1").fetchone()[0]
        grouped = db.execute(
            "SELECT COUNT(*) FROM books WHERE active=1 AND series_id IS NOT NULL").fetchone()[0]
        review = db.execute(
            "SELECT COUNT(*) FROM books WHERE active=1 AND review_reason<>''").fetchone()[0]
        groups = db.execute("SELECT COUNT(*) FROM series").fetchone()[0]
        covers = db.execute("SELECT COUNT(*) FROM cover_overrides WHERE length(image)>1").fetchone()[0]
        record = db.execute("SELECT value FROM library_meta WHERE key='last_saved_at'").fetchone()
        destination = db_path()
        integrity = db.execute("PRAGMA quick_check(1)").fetchone()[0]
        return {"count": active, "database": str(destination), "grouped": grouped,
                "review": review, "series": groups, "automatic": True,
                "persistent": integrity == "ok", "db_bytes": destination.stat().st_size,
                "custom_covers": covers, "last_saved_at": record[0] if record else None,
                "journal_mode": db.execute("PRAGMA journal_mode").fetchone()[0]}


@router.get("/preview")
def preview():
    with LOCK, database() as db:
        return organize(db, apply=False)


@router.post("/organize")
def auto_organize():
    with LOCK, database() as db:
        return organize(db)


@router.post("/refresh")
def refresh():
    from api_routes import reading_drive
    # Google Drive must be read successfully before touching existing metadata.
    # reading_drive.catalogue also updates its allowed media IDs for the reader.
    result = reading_drive.catalogue()
    listing = result.get("books", [])
    if len(listing) > 4000:
        raise HTTPException(413, "Too many books")
    books = []
    for item in listing:
        file_id = identifier(str(item["id"]))
        cover_id = item.get("cover")
        if cover_id is not None:
            identifier(str(cover_id))
        books.append((file_id, str(item["title"])[:250], str(item.get("group") or "")[:300], cover_id))
    with LOCK, database() as db:
        db.execute("UPDATE books SET active=0")
        for file_id, title, folder, cover in books:
            db.execute("""
                INSERT INTO books(id,title,source_title,folder_name,cover_id,active)
                VALUES(?,?,?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET
                    title=CASE WHEN books.manual_title=1 THEN books.title ELSE excluded.title END,
                    source_title=excluded.source_title,
                    folder_name=excluded.folder_name,
                    cover_id=excluded.cover_id,
                    active=1
            """, (file_id, title, title, folder, cover))
        report = organize(db)
        return {"synced": len(books), "database": str(db_path()), **report}


@router.post("/series")
def add_series(info: SeriesInput):
    name = info.title.strip()
    if not name:
        raise HTTPException(422, "Series name required")
    value = str(uuid.uuid4())
    with LOCK, database() as db:
        for existing in db.execute("SELECT id,title FROM series"):
            if normalized(existing["title"]) == normalized(name):
                return {"id": existing["id"], "title": existing["title"], "already_exists": True}
        db.execute("INSERT INTO series(id,title,description,genre) VALUES(?,?,?,?)",
                   (value, name, info.description, info.genre))
    return {"id": value, "title": name, "already_exists": False}


@router.post("/series/{value}")
def edit_series(value: str, info: SeriesEdit):
    series_id(value)
    updates = {}
    fields = info.model_fields_set
    for field in ("title", "description", "genre", "position"):
        if field in fields:
            entry = getattr(info, field)
            if entry is None:
                raise HTTPException(422, "Null series metadata is not allowed")
            updates[field] = entry.strip() if isinstance(entry, str) else entry
    if "title" in updates and not updates["title"]:
        raise HTTPException(422, "Series title required")
    with LOCK, database() as db:
        if not db.execute("SELECT 1 FROM series WHERE id=?", (value,)).fetchone():
            raise HTTPException(404, "Series not found")
        if updates:
            sql = ", ".join(key+"=?" for key in updates)
            db.execute("UPDATE series SET "+sql+" WHERE id=?", (*updates.values(), value))
    return {"updated": True}


@router.post("/merge")
def merge_series(info: SeriesMerge):
    source, target = series_id(info.source), series_id(info.target)
    if source == target:
        raise HTTPException(422, "Cannot merge series into itself")
    with LOCK, database() as db:
        series_exists(db, source)
        series_exists(db, target)
        db.execute(
            "UPDATE books SET series_id=?,manual_series=1 WHERE series_id=?",
            (target,source))
        db.execute("DELETE FROM series WHERE id=?", (source,))
    return {"merged": True}


@router.post("/book")
def edit_book(info: EditBook):
    identifier(info.id)
    with LOCK, database() as db:
        if not db.execute("SELECT 1 FROM books WHERE id=? AND active=1", (info.id,)).fetchone():
            raise HTTPException(404, "Book not found")
        fields = info.model_fields_set
        if "series_id" in fields:
            series_exists(db, info.series_id)
        updates = {}
        if "title" in fields:
            if not info.title or not info.title.strip():
                raise HTTPException(422, "Book title required")
            updates.update(title=info.title.strip(),manual_title=1)
        if "series_id" in fields:
            updates.update(series_id=info.series_id,manual_series=1)
        if "issue_number" in fields:
            updates.update(issue_number=info.issue_number,manual_issue=1)
        if "position" in fields:
            updates.update(position=info.position,manual_position=1)
        for field in ("published", "hidden"):
            if field in fields:
                value = getattr(info, field)
                if value is None:
                    raise HTTPException(422, field+" must be a boolean")
                updates[field] = int(value)
        if updates:
            db.execute("UPDATE books SET "+", ".join(key+"=?" for key in updates)+" WHERE id=?",
                       (*updates.values(),info.id))
        # Rebuild review flags after the owner's modifications while preserving overrides.
        organize(db)
    return {"updated": True}


@router.post("/bulk")
def bulk_edit(info: BulkEdit):
    if len(info.ids) != len(set(info.ids)):
        raise HTTPException(422, "Duplicate book identifiers")
    for value in info.ids:
        identifier(value)
    fields = info.model_fields_set
    if not fields.intersection({"series_id", "hidden", "published"}):
        raise HTTPException(422, "Choose a bulk action")
    with LOCK, database() as db:
        if "series_id" in fields:
            series_exists(db, info.series_id)
        updates = {}
        if "series_id" in fields:
            updates.update(series_id=info.series_id,manual_series=1)
        for field in ("hidden", "published"):
            if field in fields:
                if getattr(info, field) is None:
                    raise HTTPException(422, "Expected boolean")
                updates[field] = int(getattr(info, field))
        sql = "UPDATE books SET " + ", ".join(k+"=?" for k in updates) + " WHERE id=? AND active=1"
        affected = 0
        for value in info.ids:
            affected += db.execute(sql, (*updates.values(), value)).rowcount
        organize(db)
    return {"updated": affected}


@router.post("/reorder")
def reorder_books(info: Reorder):
    if len(set(info.ids)) != len(info.ids):
        raise HTTPException(422, "Duplicate books in ordering")
    for value in info.ids:
        identifier(value)
    with LOCK, database() as db:
        placeholders = ",".join("?" for _ in info.ids)
        rows = db.execute(
            f"SELECT id,series_id FROM books WHERE active=1 AND id IN ({placeholders})",
            info.ids).fetchall()
        if len(rows) != len(info.ids) or len({row["series_id"] for row in rows}) != 1:
            raise HTTPException(422, "Reordering requires books from the same series")
        for index, value in enumerate(info.ids):
            db.execute("UPDATE books SET position=?,manual_position=1 WHERE id=?",
                       ((index+1)*10,value))
    return {"updated": len(info.ids)}


@router.post("/book/{value}/auto")
def reset_auto(value: str):
    identifier(value)
    with LOCK, database() as db:
        if not db.execute("SELECT 1 FROM books WHERE id=? AND active=1", (value,)).fetchone():
            raise HTTPException(404, "Book not found")
        db.execute("UPDATE books SET manual_series=0,manual_issue=0,manual_position=0,manual_title=0,"
                   "title=source_title WHERE id=?", (value,))
        return organize(db)


@router.delete("/series/{value}")
def delete_series(value: str):
    series_id(value)
    with LOCK, database() as db:
        # Explicitly detached books must not be automatically regrouped next refresh.
        db.execute("UPDATE books SET series_id=NULL,manual_series=1 WHERE series_id=?", (value,))
        db.execute("DELETE FROM series WHERE id=?", (value,))
        organize(db)
    return {"deleted": True}
