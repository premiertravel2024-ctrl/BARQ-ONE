"""Opt-in, local-only document content search over the consented metadata index.

No model, cloud service or external process receives document contents. Extraction is
bounded to resist enormous files and corrupted Office/PDF archives. All returned hits
are re-checked against the current allowlist, not merely a historic index snapshot.
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from contextlib import closing
from xml.etree import ElementTree

from core.paths import state_file
from computer_control.safety.policy import contained

TEXT_EXT = {'.txt', '.md', '.markdown', '.rst', '.py', '.js', '.jsx', '.ts', '.tsx',
            '.json', '.csv', '.log', '.html', '.css', '.yaml', '.yml', '.xml', '.sql'}
DOC_EXT = {'.docx', '.pdf', '.xlsx'}
MAX_TEXT_BYTES = 1_000_000
MAX_FILE_BYTES = 12_000_000
_lock = threading.RLock()
_cancel = threading.Event()
_worker: threading.Thread | None = None
_progress = {'status': 'idle', 'indexed': 0, 'skipped': 0, 'error': ''}


def _db_path():
    return state_file('device_content_index.sqlite3')


def _db():
    connection = sqlite3.connect(str(_db_path()), timeout=12)
    try:
        connection.execute('PRAGMA busy_timeout=12000')
        # FTS5 is bundled with the SQLite distributed by supported CPython.
        connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(path UNINDEXED, body, tokenize='unicode61')")
        connection.execute('CREATE TABLE IF NOT EXISTS stamps(path TEXT PRIMARY KEY, modified REAL, size INTEGER)')
        connection.commit()
        return connection
    except BaseException:
        connection.close()
        raise


def _read_text(path: Path, size: int) -> str:
    suffix = path.suffix.lower()
    if size < 1 or size > MAX_FILE_BYTES or suffix not in TEXT_EXT | DOC_EXT:
        return ''
    try:
        if suffix in TEXT_EXT:
            if size > MAX_TEXT_BYTES:
                return ''
            data = path.read_bytes()
            if b'\0' in data:
                return ''
            text = data.decode('utf-8-sig', errors='replace')
        elif suffix == '.xlsx':
            parts=[];total=0
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if not (info.filename=='xl/sharedStrings.xml' or re.fullmatch(r'xl/worksheets/sheet[0-9]+.xml',info.filename)):continue
                    total+=info.file_size
                    if total>5*MAX_TEXT_BYTES:return ''
                    root=ElementTree.fromstring(archive.read(info))
                    parts.extend(node.text or '' for node in root.iter() if node.tag.endswith(('}t','}v')))
                    if sum(map(len,parts))>MAX_TEXT_BYTES:break
            text=' '.join(parts)
        elif suffix == '.docx':
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo('word/document.xml')
                if info.file_size > 2 * MAX_TEXT_BYTES:
                    return ''
                raw = archive.read(info, pwd=None)
                root = ElementTree.fromstring(raw)
                text = ' '.join(node.text or '' for node in root.iter() if node.tag.endswith('}t'))
        else:
            try:
                import fitz
            except ImportError:
                return ''
            with fitz.open(str(path)) as pdf:
                pages = []
                for page in pdf:
                    pages.append(page.get_text('text'))
                    if sum(map(len, pages)) >= MAX_TEXT_BYTES:
                        break
                text = '\n'.join(pages)
        from computer_control.safety.policy import redact
        return redact(text[:MAX_TEXT_BYTES])
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile,
            zipfile.LargeZipFile, KeyError, ElementTree.ParseError):
        return ''


def _run(roots: list[str]):
    from services import device_index
    indexed = skipped = 0
    completed = False
    try:
        with closing(_db()) as db, closing(device_index._connect()) as inventory:
            cursor = inventory.execute('SELECT path,size,modified FROM files ORDER BY path')
            for path, size, modified in cursor:
                if _cancel.is_set() or not device_index.settings().get('content_enabled'):
                    break
                candidate = Path(path)
                # Old metadata is not authorization to open a file now.
                if (candidate.suffix.lower() not in TEXT_EXT | DOC_EXT
                        or not device_index._safe_path_in_roots(candidate, [Path(r) for r in roots])
                        or not any(contained(str(candidate), [root]) for root in roots)):
                    skipped += 1
                    continue
                try:
                    st = candidate.lstat()
                    if not candidate.is_file() or candidate.is_symlink() or st.st_size != size or st.st_mtime != modified:
                        skipped += 1
                        continue
                except OSError:
                    skipped += 1
                    continue
                stamp = db.execute('SELECT modified,size FROM stamps WHERE path=?', (path,)).fetchone()
                if stamp == (modified, size):
                    continue
                body = _read_text(candidate, size)
                db.execute('DELETE FROM docs WHERE path=?', (path,))
                db.execute('DELETE FROM stamps WHERE path=?', (path,))
                if body.strip():
                    db.execute('INSERT INTO docs(path,body) VALUES (?,?)', (path, body))
                    db.execute('INSERT INTO stamps(path,modified,size) VALUES (?,?,?)', (path, modified, size))
                    indexed += 1
                else:
                    skipped += 1
                if (indexed + skipped) % 30 == 0:
                    db.commit()
                    with _lock: _progress.update(indexed=indexed, skipped=skipped)
            else:
                completed = True
            if completed and not _cancel.is_set():
                # Remove removed files and paths no longer inside the current consent scope.
                existing = db.execute('SELECT path FROM stamps').fetchall()
                for (path,) in existing:
                    if not (device_index._safe_path_in_roots(Path(path), [Path(r) for r in roots])
                            and any(contained(path, [root]) for root in roots)
                            and inventory.execute('SELECT 1 FROM files WHERE path=?', (path,)).fetchone()):
                        db.execute('DELETE FROM docs WHERE path=?', (path,))
                        db.execute('DELETE FROM stamps WHERE path=?', (path,))
            db.commit()
        with _lock: _progress.update(status='ready' if completed else 'cancelled', indexed=indexed, skipped=skipped)
    except (sqlite3.DatabaseError, OSError) as exc:
        with _lock: _progress.update(status='failed', error=type(exc).__name__)
    finally:
        if not device_index.settings().get('content_enabled'):
            _erase_disk()


def _erase_disk():
    for suffix in ('', '-wal', '-shm'):
        try: Path(str(_db_path()) + suffix).unlink(missing_ok=True)
        except OSError: pass


def disable():
    _cancel.set()
    with _lock:
        worker = _worker
    if worker and worker.is_alive():
        worker.join(timeout=3)
    if not (worker and worker.is_alive()):
        _erase_disk()
    with _lock: _progress.update(status='disabled', indexed=0, skipped=0, error='')


def refresh(allowed_folders: list[str]):
    from services import device_index
    cfg = device_index.settings()
    if not cfg.get('enabled') or not cfg.get('content_enabled'):
        return {'status': 'permission_required'}
    roots = device_index.scan_roots(cfg, allowed_folders)
    if not roots:
        return {'status': 'no_roots'}
    global _worker
    with _lock:
        if _worker and _worker.is_alive():
            return dict(_progress)
        _cancel.clear()
        _progress.update(status='indexing', indexed=0, skipped=0, error='')
        _worker = threading.Thread(target=_run, args=([str(p) for p in roots],),
                                   name='barq-content-indexer', daemon=True)
        _worker.start()
        return dict(_progress)


def status():
    with _lock: return dict(_progress)


def search(query: str, allowed_folders: list[str], limit: int = 12):
    from services import device_index
    cfg = device_index.settings()
    if not cfg.get('enabled') or not cfg.get('content_enabled'):
        return {'status': 'permission_required', 'results': []}
    if not isinstance(query, str) or len(query.strip()) < 2 or len(query) > 150:
        return {'status': 'invalid_query', 'results': []}
    roots = device_index.scan_roots(cfg, allowed_folders)
    if not roots:
        return {'status': 'no_roots', 'results': []}
    # Avoid FTS query syntax: search for each literal unicode word as a token.
    words = [w for w in re.findall(r'[^\W_]+', query.casefold(), flags=re.UNICODE) if len(w) > 1][:8]
    if not words:
        return {'status': 'invalid_query', 'results': []}
    expression = ' AND '.join('"' + word.replace('"', '') + '"' for word in words)
    try:
        with closing(_db()) as db:
            rows = db.execute('SELECT path, snippet(docs,1,"[","]","…",12) FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?',
                              (expression, min(40, max(1, int(limit)))*8)).fetchall()
        results = []
        for path, snippet in rows:
            candidate = Path(path)
            if (device_index._safe_path_in_roots(candidate, roots) and not candidate.is_symlink()
                    and candidate.is_file()
                    and any(contained(path, [str(root)]) for root in roots)):
                results.append({'name': candidate.name, 'extension': candidate.suffix.lower(),
                                'path': path, 'snippet': snippet[:260], 'source': 'local-content'})
                if len(results) >= limit: break
        return {'status': 'ok', 'results': results, 'engine': 'local-content', 'index': status(),
                'note': 'النتائج محلية؛ لا ترسل مقتطفات الملف إلى الموديلات السحابية تلقائيًا.'}
    except (sqlite3.DatabaseError, OSError):
        return {'status': 'index_unavailable', 'results': []}
