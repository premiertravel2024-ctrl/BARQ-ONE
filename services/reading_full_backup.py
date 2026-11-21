"""Owner-triggered, verified ZIP snapshots of both SQLite and archived PDF files.

This is a disaster-recovery export, not an update mechanism: never overwrite a
live database or delete the owner's Google Drive originals automatically.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Thread, RLock
from zipfile import ZipFile, ZIP_STORED, BadZipFile
import json
import os
import shutil
import sqlite3
import uuid

LOCK = RLock()
_worker: Thread | None = None
_state = {"running": False, "copied": 0, "total": 0, "file": "", "bytes": 0, "error": ""}


def status() -> dict:
    with LOCK:
        return dict(_state)


def start_full_backup() -> dict:
    """Create one complete, verifiable backup in BARQ DATABASE/backups."""
    global _worker
    with LOCK:
        if _worker is not None and _worker.is_alive():
            return dict(_state)
        _state.update(running=True, copied=0, total=0, error="", file="", bytes=0)
        _worker = Thread(target=_build_backup, name="barq-complete-library-backup", daemon=True)
        _worker.start()
        return dict(_state)


def _build_backup() -> None:
    from api_routes.reading_local_library import LOCK as DB_LOCK, database, db_path
    from api_routes.reading import _migrate_legacy_covers
    from services.reading_book_archive import archive_path, _validate_file

    database_file = db_path()
    backup_dir = database_file.parent / "backups"
    staging_db: Path | None = None
    staging_zip: Path | None = None
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=backup_dir, prefix=".barq-archive-", suffix=".sqlite3", delete=False) as temp:
            staging_db = Path(temp.name)
        # Capture an ACID-consistent SQLite snapshot, including WAL commits.
        with DB_LOCK, database() as db:
            _migrate_legacy_covers(db)
            db.commit()
            with closing(sqlite3.connect(str(staging_db))) as copy:
                db.backup(copy)
                if copy.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                    raise ValueError("SQLite snapshot did not pass integrity verification")
        with closing(sqlite3.connect(str(staging_db))) as snapshot:
            # Never mislabel a partially mirrored Drive library as a complete
            # backup. The owner should finish local PDF copying first.
            total_books = snapshot.execute("SELECT COUNT(*) FROM books WHERE active=1").fetchone()[0]
            saved_books = snapshot.execute(
                "SELECT COUNT(*) FROM books b JOIN book_archives a ON a.file_id=b.id WHERE b.active=1"
            ).fetchone()[0]
            if total_books != saved_books:
                raise ValueError("Some books are not copied offline yet; finish archiving before full backup")
            rows = snapshot.execute("SELECT digest,size FROM book_archives").fetchall()
        # A physical PDF is written once even when multiple books reference it.
        unique = {str(digest): int(size) for digest, size in rows}
        with LOCK:
            _state["total"] = len(unique)
        files = []
        for digest, size in unique.items():
            path = archive_path(digest)
            if not _validate_file(path, digest, size):
                raise ValueError("A recorded PDF is missing or damaged; repair the local archive first")
            files.append((digest, size, path))
        # Avoid writing a partial multi-GB backup onto a nearly full external disk.
        required = staging_db.stat().st_size + sum(size for _, size, _ in files)
        if shutil.disk_usage(backup_dir).free < required + 64 * 1024 * 1024:
            raise OSError("Insufficient space for a complete backup")
        with NamedTemporaryFile(dir=backup_dir, prefix=".barq-library-", suffix=".part", delete=False) as temp:
            staging_zip = Path(temp.name)
        manifest = {
            "format": "barq-library-complete-v1",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pdf_files": len(files),
            "pdf_bytes": sum(size for _, size, _ in files),
            "sqlite": "barq_library.sqlite3",
            "books_dir": "books/",
        }
        with ZipFile(staging_zip, "w", compression=ZIP_STORED, allowZip64=True) as packed:
            packed.write(staging_db, "barq_library.sqlite3")
            packed.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True))
            for digest, size, path in files:
                # Content-addressed PDFs are immutable: never rename/mutate the source.
                packed.write(path, f"books/{digest}.pdf")
                with LOCK:
                    _state["copied"] += 1
        with ZipFile(staging_zip, "r", allowZip64=True) as check:
            if check.testzip() is not None:
                raise ValueError("The ZIP archive failed CRC verification")
            if "barq_library.sqlite3" not in check.namelist() or "manifest.json" not in check.namelist():
                raise ValueError("Incomplete library backup")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        destination = backup_dir / f"BARQ_FULL_LIBRARY_{timestamp}_{uuid.uuid4().hex[:8]}.zip"
        staging_zip.replace(destination)
        with LOCK:
            _state["file"] = str(destination)
            _state["bytes"] = destination.stat().st_size
    except (OSError, sqlite3.Error, ValueError, BadZipFile, RuntimeError) as exc:
        with LOCK:
            _state["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    finally:
        for temporary in (staging_db, staging_zip):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        with LOCK:
            _state["running"] = False
