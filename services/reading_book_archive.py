"""Private, content-addressed offline copies of the owner's Google Drive PDFs.

The SQLite book_archives table owns the verified manifest; complete PDF bytes
live beside that database in <BARQ DATABASE>/books/<sha256>.pdf. No user PDFs are
uploaded to an online room, server or another Google account.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock, Thread
import os
import re
import shutil

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse

MAX_PDF = 64 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{10,160}")
DIGEST = re.compile(r"[0-9a-f]{64}")
LOCK = RLock()
_worker: Thread | None = None
_state = {"processed": 0, "downloaded": 0, "failed": 0, "error": ""}


def archive_dir() -> Path:
    from api_routes.reading_local_library import db_path
    return db_path().parent / "books"


def archive_path(digest: str) -> Path:
    if not DIGEST.fullmatch(digest):
        raise ValueError("Invalid PDF digest")
    return archive_dir() / (digest + ".pdf")


def _validate_file(path: Path, digest: str, size: int) -> bool:
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
        hasher = sha256()
        with path.open("rb") as source:
            if not source.read(5) == b"%PDF-":
                return False
            source.seek(0)
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest() == digest
    except OSError:
        return False


def archived_pdf(file_id: str):
    """Return a local, hashed PDF even when Drive OAuth is offline."""
    if not ID.fullmatch(file_id):
        return None
    from api_routes.reading_local_library import LOCK as DB_LOCK, database
    with DB_LOCK, database() as db:
        row = db.execute(
            "SELECT digest,size FROM book_archives WHERE file_id=?", (file_id,)
        ).fetchone()
    if row is None:
        return None
    digest, size = str(row["digest"]), int(row["size"])
    if not DIGEST.fullmatch(digest) or not 5 <= size <= MAX_PDF:
        return None
    path = archive_path(digest)
    if not _validate_file(path, digest, size):
        return None
    return FileResponse(
        path, media_type="application/pdf",
        filename=None, headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Accept-Ranges": "bytes",
        },
    )


def _download_pdf(file_id: str, expected_md5: str | None = None):
    """Stream the *allowed* owner's PDF with size bounds and atomic replacement."""
    from api_routes import reading_drive
    with reading_drive.LOCK:
        if reading_drive.items.get(file_id) != "application/pdf":
            raise ValueError("PDF is not in the connected owner's Drive folder")
        headers = reading_drive.auth()
    headers["Accept-Encoding"] = "identity"
    folder = archive_dir()
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with httpx.stream(
            "GET", f"{reading_drive.API}/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
            headers=headers, timeout=httpx.Timeout(50.0, connect=10.0),
        ) as response:
            if response.status_code != 200:
                raise ValueError("Google Drive did not provide a complete PDF")
            length = response.headers.get("content-length")
            if length and length.isdecimal() and int(length) > MAX_PDF:
                raise ValueError("PDF exceeds the 64 MB archive limit")
            if shutil.disk_usage(folder).free < MAX_PDF + (32 * 1024 * 1024):
                raise OSError("Not enough free disk space to archive a PDF")
            with NamedTemporaryFile(dir=folder, prefix=".barq-download-", suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                digest = sha256()
                count = 0
                first = True
                for chunk in response.iter_bytes(chunk_size=65536):
                    if not chunk:
                        continue
                    if first and not chunk.startswith(b"%PDF-"):
                        raise ValueError("Drive returned non-PDF content")
                    first = False
                    count += len(chunk)
                    if count > MAX_PDF:
                        raise ValueError("PDF exceeds the 64 MB archive limit")
                    handle.write(chunk)
                    digest.update(chunk)
                if count < 5 or (length and length.isdecimal() and count != int(length)):
                    raise ValueError("Incomplete PDF download")
                handle.flush()
                os.fsync(handle.fileno())
        checksum = digest.hexdigest()
        result = archive_path(checksum)
        if result.exists() and _validate_file(result, checksum, count):
            temporary.unlink(missing_ok=True)
        else:
            temporary.replace(result)
        return checksum, count
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _process_archive():
    from api_routes.reading_local_library import LOCK as DB_LOCK, database
    from api_routes import reading_drive
    with LOCK:
        _state.update(processed=0, downloaded=0, failed=0, error="")
    try:
        # Refresh the allowlist from the owner's selected Drive folder. Never
        # bulk-fetch arbitrary IDs supplied by another account or browser.
        online = reading_drive.catalogue()["books"]
        allowed = {str(book["id"]) for book in online}
        with DB_LOCK, database() as db:
            pending = [dict(row) for row in db.execute(
                "SELECT b.id,b.source_md5,a.source_md5 AS saved_md5,a.digest,a.size "
                "FROM books b LEFT JOIN book_archives a ON a.file_id=b.id "
                "WHERE b.active=1 ORDER BY b.position,b.title"
            ) if row["id"] in allowed]
        for row in pending:
            from api_routes.reading_local_library import db_path
            if not db_path().parent.is_dir():
                raise OSError("The configured BARQ database drive is unavailable")
            try:
                digest = row["digest"]
                same_source = not row["source_md5"] or row["source_md5"] == row["saved_md5"]
                if digest and same_source and _validate_file(
                    archive_path(digest), digest, row["size"]
                ):
                    continue
                checksum, count = _download_pdf(row["id"], row["source_md5"])
                with DB_LOCK, database() as db:
                    db.execute(
                        "INSERT INTO book_archives(file_id,digest,size,source_md5,stored_at) "
                        "VALUES(?,?,?,?,?) ON CONFLICT(file_id) DO UPDATE SET "
                        "digest=excluded.digest,size=excluded.size,"
                        "source_md5=excluded.source_md5,stored_at=excluded.stored_at",
                        (row["id"], checksum, count, row["source_md5"],
                         datetime.now(timezone.utc).isoformat(timespec="seconds")),
                    )
                with LOCK:
                    _state["downloaded"] += 1
            except (httpx.HTTPError, OSError, ValueError, HTTPException) as exc:
                with LOCK:
                    _state["failed"] += 1
                    _state["error"] = f"Some PDFs could not be copied: {type(exc).__name__}"
            finally:
                with LOCK:
                    _state["processed"] += 1
    except (httpx.HTTPError, OSError, ValueError, HTTPException) as exc:
        with LOCK:
            _state["error"] = f"Book archive was interrupted: {type(exc).__name__}"


def start_archive(*, enabled: bool = False) -> dict:
    """Kick off a single low-concurrency archive worker; never block the UI."""
    from api_routes.reading_local_library import LOCK as DB_LOCK, database
    from api_routes import reading_drive
    global _worker
    if enabled:
        with DB_LOCK, database() as db:
            db.execute(
                "INSERT INTO library_meta(key,value) VALUES('archive_enabled','1') "
                "ON CONFLICT(key) DO UPDATE SET value='1'"
            )
    with DB_LOCK, database() as db:
        row = db.execute("SELECT value FROM library_meta WHERE key='archive_enabled'").fetchone()
    if not row or row["value"] != "1":
        return archive_status()
    with reading_drive.LOCK:
        if not reading_drive.remembered():
            if enabled:
                raise HTTPException(409, "Connect your own Google Drive before archiving books")
            return archive_status()
    with LOCK:
        if _worker is None or not _worker.is_alive():
            _worker = Thread(target=_process_archive, name="barq-book-archive", daemon=True)
            _worker.start()
    return archive_status()


def archive_status() -> dict:
    from api_routes.reading_local_library import LOCK as DB_LOCK, database
    with DB_LOCK, database() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM books WHERE active=1"
        ).fetchone()[0]
        archived = db.execute(
            "SELECT COUNT(*) FROM book_archives a "
            "JOIN books b ON b.id=a.file_id AND b.active=1"
        ).fetchone()[0]
        size = db.execute(
            "SELECT COALESCE(SUM(size),0) FROM book_archives a "
            "JOIN books b ON b.id=a.file_id AND b.active=1"
        ).fetchone()[0]
        enabled = db.execute(
            "SELECT value FROM library_meta WHERE key='archive_enabled'"
        ).fetchone()
    with LOCK:
        running = bool(_worker and _worker.is_alive())
        state = dict(_state)
    return {
        "enabled": bool(enabled and enabled["value"] == "1"),
        "running": running, "total": count, "archived": archived,
        "bytes": size, "directory": str(archive_dir()),
        **state,
    }
