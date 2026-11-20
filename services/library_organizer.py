"""Deterministic, offline organizer for an owner's Google Drive reading catalogue.

No model/API calls: only trusted folder names and clear filename sequences.
Owner-edited titles, series, issue numbers and positions always win.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re
import unicodedata
import uuid

NAMESPACE = uuid.UUID("72666afd-28cb-48a3-8818-652aa815451e")
GENERIC = {
    "كتب", "كتاب", "روايات", "الروايات", "قصص", "المكتبه", "مكتبه", "المكتبة",
    "books", "book", "pdf", "pdfs", "novels", "stories", "library", "arabic",
    "english", "other", "مجلد", "الجديد", "world", "العالميه", "المصريه"
}
# Only explicit, distinctive series identifiers can be detected from a filename
# when there is no clearly named group folder.
KNOWN = {
    "ما وراء الطبيعة": ("ما وراء الطبيعة", "kat"),
    "رجل المستحيل": ("رجل المستحيل",),
    "ملف المستقبل": ("ملف المستقبل",),
    "فانتازيا": ("فانتازيا",),
    "سافاري": ("سافاري",),
    "هاري بوتر": ("هاري بوتر", "harry potter"),
    "أرسين لوبين": ("أرسين لوبين", "ارسين لوبين", "arsene lupin"),
    "فلاش": ("فلاش",),
}


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    value = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", value)
    value = re.sub("[أإآ]", "ا", value).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", value.casefold()).strip()


def number_from_filename(title: str, series_name: str = "") -> int | None:
    value = normalized(title)
    series_value = normalized(series_name)
    # Prefix: 003 - ..., العدد 3, الجزء 3, kat003, kat-sp-003.
    patterns = (
        r"^(?:kat[\s_-]*(?:sp[\s_-]*)?|no[\s.#_-]*|issue[\s.#_-]*|العدد[\s.#_-]*|الجزء[\s.#_-]*|ج[\s.#_-]*)(\d{1,4})(?=\D|$)",
        r"^(\d{1,4})(?=[\s._\-–—]|$)",
    )
    for pattern in patterns:
        found = re.search(pattern, value)
        if found and 1 <= int(found[1]) <= 999:
            return int(found[1])
    if series_value and value.startswith(series_value):
        remaining = value[len(series_value):].lstrip(" ._-–—#")
        found = re.match(r"^(?:العدد\s*|الجزء\s*|book\s*|part\s*)?(\d{1,3})(?=\D|$)", remaining)
        if found and 1 <= int(found[1]) <= 999:
            return int(found[1])
    return None


def group_candidates(rows: list[dict]) -> dict[str, tuple[str, str]]:
    """Only infer a folder as a series if it has at least two PDF books."""
    folders = defaultdict(list)
    for book in rows:
        path = str(book.get("folder_name") or "").strip()
        if path:
            folders[path].append(book)
    result = {}
    for path, items in folders.items():
        name = path.split(" / ")[-1].strip()
        if len(items) > 1 and normalized(name) not in GENERIC and len(name) > 2:
            result[path] = ("folder:" + normalized(path), name[:120])
    return result


def infer(book: dict, folders: dict[str, tuple[str, str]]) -> tuple[str, str, int | None, str]:
    title = str(book["source_title"])
    folder = book.get("folder_name") or ""
    if folder in folders:
        key, name = folders[folder]
        return key, name, number_from_filename(title, name), "folder"
    value = normalized(title)
    for name, aliases in KNOWN.items():
        if any(
            value.startswith(normalized(alias) + sep) or value == normalized(alias)
            for alias in aliases for sep in (" ", "-", "_", ".", "")
        ):
            return "known:" + normalized(name), name, number_from_filename(title, name), "filename"
    return "", "", None, "unclassified"


def organize(db, *, apply: bool = True) -> dict:
    """Compute a stable proposal or apply it transactionally within caller's transaction."""
    raw = db.execute(
        "SELECT id,source_title,folder_name,series_id,issue_number,position,"
        "manual_series,manual_issue,manual_position FROM books WHERE active=1"
    ).fetchall()
    books = [dict(row) for row in raw]
    folders = group_candidates(books)
    existing = {row["source_key"]: row["id"] for row in
                db.execute("SELECT id,source_key FROM series WHERE source_key IS NOT NULL")}
    by_title = {normalized(row["title"]): row["id"] for row in
                db.execute("SELECT id,title FROM series")}
    proposals = {}
    new_series = {}
    assigned = 0
    detected_numbers = 0
    unresolved = 0
    for book in books:
        source_key, series_name, issue, reason = infer(book, folders)
        if source_key:
            series_id = existing.get(source_key) or by_title.get(normalized(series_name))
            if not series_id:
                series_id = str(uuid.uuid5(NAMESPACE, source_key))
                new_series[series_id] = (series_name, source_key)
            elif source_key not in existing:
                new_series.setdefault(series_id, (None, source_key))
        else:
            series_id = None
        chosen = book["series_id"] if book["manual_series"] else series_id
        if chosen:
            assigned += 1
        chosen_issue = book["issue_number"] if book["manual_issue"] else issue
        if chosen_issue:
            detected_numbers += 1
        review = "missing-issue" if chosen and chosen_issue is None else (
            "unclassified" if chosen is None else ""
        )
        if review:
            unresolved += 1
        proposals[book["id"]] = {
            "series_id": chosen, "issue_number": chosen_issue, "review_reason": review,
            "matched_by": reason,
        }
    report = {
        "books": len(books),
        "series": len({p["series_id"] for p in proposals.values() if p["series_id"]}),
        "assigned": assigned,
        "numbered": detected_numbers,
        "review": unresolved,
        "new_series": len([id for id,(name,_) in new_series.items() if name]),
    }
    if not apply:
        return {**report, "preview": True}
    for identifier, (name, source_key) in new_series.items():
        if name:
            db.execute("INSERT OR IGNORE INTO series(id,title,source_key) VALUES (?,?,?)",
                       (identifier,name,source_key))
        else:
            db.execute("UPDATE series SET source_key=COALESCE(source_key,?) WHERE id=?",
                       (source_key,identifier))
    for identifier, proposal in proposals.items():
        db.execute(
            "UPDATE books SET series_id=?,issue_number=?,review_reason=? WHERE id=?",
            (proposal["series_id"],proposal["issue_number"],proposal["review_reason"],identifier)
        )
    return {**report, "preview": False}
