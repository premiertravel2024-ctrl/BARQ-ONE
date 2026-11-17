"""Bounded UI context and read-only catalogue discovery for BARQ's assistants."""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

Section = Literal['center', 'chat', 'voice', 'mission', 'library', 'installed', 'tools',
                  'monitor', 'resources', 'wallpapers', 'watch', 'music', 'stories',
                  'automation', 'settings', 'playground']
Catalogue = Literal['books', 'movies', 'series', 'spotify', 'anghami', 'local_music', 'tools']
router = APIRouter(prefix='/v1/app-context', tags=['BARQ application context'])
_lock = threading.Lock()
_snapshot = None
_snapshot_at = 0.0

SECTION_ALIASES = {
    'center': 'مركز الاوامر|command center',
    'chat': 'الشات|المحادثه|المحادثة|chat',
    'voice': 'المساعد الصوتي|voice assistant',
    'mission': 'المهام|مهام برق|mission control',
    'library': 'مكتبه البرامج|مكتبه openhub|مكتبة البرامج|مكتبة openhub|openhub',
    'installed': 'البرامج المثبته|البرامج المثبتة|installed software',
    'tools': 'الادوات|النماذج والادوات|ادوات برق|tools|ai models',
    'monitor': 'مراقبه النظام|مراقبة النظام|system monitor',
    'resources': 'توفير الموارد|resource saver',
    'wallpapers': 'الخلفيات الحيه|الخلفيات الحية|live wallpapers',
    'watch': 'السينما|سينما برق|الافلام|cinema|watch together',
    'music': 'الموسيقي|الاغاني|موسيقي برق|music|spotify|سبوتيفاي|انغامي|anghami',
    'stories': 'المكتبه|المكتبة|الكتب|مكتبه القراءه|مكتبة القراءة|حكايات برق|books|reading library',
    'automation': 'الاتمته|الاتمتة|automation',
    'settings': 'الاعدادات|settings',
}
_SCOPE = {
    'كتاب': 'books', 'سلسلة': 'books', 'سلسله': 'books', 'رواية': 'books', 'روايه': 'books',
    'book': 'books', 'فيلم': 'movies', 'movie': 'movies', 'مسلسل': 'series', 'series': 'series',
    'اداة': 'tools', 'اداه': 'tools', 'tool': 'tools', 'اغنية': 'local_music', 'اغنيه': 'local_music',
    'song': 'local_music',
}
_PROVIDER = {'spotify': 'spotify', 'سبوتيفاي': 'spotify', 'anghami': 'anghami', 'انغامي': 'anghami'}


def normalized(text: str) -> str:
    return re.sub(r'\s+', ' ', ''.join(
        char for char in unicodedata.normalize('NFKD', text.casefold())
        if not unicodedata.combining(char)
    ).translate(str.maketrans({'ى': 'ي', 'ـ': None}))).strip()


class UIItem(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    label: str = Field(default='', max_length=90)


class View(BaseModel):
    mode: str = Field(default='', max_length=60)
    item: str = Field(default='', max_length=140)
    count: int | None = Field(default=None, ge=0, le=50000)
    status: str = Field(default='', max_length=80)


class Snapshot(BaseModel):
    section: Section
    previous: Section | None = None
    current_view: View | None = None
    previous_view: View | None = None
    books: list[UIItem] = Field(default_factory=list, max_length=40)


def read_context() -> dict:
    with _lock:
        snapshot = _snapshot
        active = time.monotonic() - _snapshot_at < 45
    if not snapshot or not active:
        return {'status': 'unavailable', 'message': 'حالة الواجهة مش متاحة حاليًا.'}
    return {'status': 'ok', 'section': snapshot.section, 'previous': snapshot.previous,
            'current_view': snapshot.current_view.model_dump(exclude_defaults=True) if snapshot.current_view else None,
            'previous_view': snapshot.previous_view.model_dump(exclude_defaults=True) if snapshot.previous_view else None}


@router.put('/state')
def set_state(body: Snapshot):
    global _snapshot, _snapshot_at
    with _lock:
        _snapshot = body
        _snapshot_at = time.monotonic()
    return {'saved': True}


@router.get('/state')
def get_state():
    return read_context()


def section_command(text: str) -> dict | None:
    command = normalized(text).strip('؟?!.,،،')
    command = re.sub(r'^(?:(?:يا برق|برق|من فضلك|لو سمحت|ممكن|please)\s+)+', '', command)
    match = re.fullmatch(r'(?:افتح(?:لي)?|روح(?: ل)?|وديني(?: ل)?|اعرض|open|go to|show)\s+(?:قسم |صفحه |صفحة |the )?(.+)', command)
    if not match:
        return None
    target = re.sub(r'\s+(?:في|جوه|داخل|in)\s+(?:التطبيق|برق|barq)$', '', match[1])
    for section, names in SECTION_ALIASES.items():
        if target in names.split('|'):
            return {'section': section, 'mode': _PROVIDER.get(target)}
    return None


def find_request(text: str) -> tuple[str, str] | None:
    command = normalized(text).strip('؟?!.,،')
    match = re.fullmatch(r'(?:(?:يا برق|برق|ممكن|لو سمحت|please)\s+)*(?:ابحث(?:لي)?|دور(?:لي)?|هات(?:لي)?|find|search)\s+(?:عن |علي |for )?(\S+)\s+(.+)', command)
    if not match:
        return None
    scope = _SCOPE.get(match[1])
    query = match[2]
    provider = re.fullmatch(r'(.+?)\s+(?:علي|في|in|on)\s+(spotify|سبوتيفاي|انغامي|anghami)', query)
    if provider and scope == 'local_music':
        return _PROVIDER[provider[2]], provider[1]
    if not scope or re.search(r'\b(?:من جهازي|عندي علي الجهاز|علي الجهاز|علي الكمبيوتر|عندي علي الهارد|من الهارد|on my pc)\b', query):
        return None
    return scope, query


@router.get('/search')
def search_catalogue(catalogue: Catalogue, q: str = Query(min_length=2, max_length=100)):
    terms = normalized(q).split()
    if not terms:
        return {'status': 'ok', 'items': []}
    if catalogue == 'tools':
        from api_routes.openhub import catalog
        items = [{'title': row['name'], 'label': row['category']} for row in catalog().values()]
    elif catalogue == 'books':
        with _lock:
            snapshot = _snapshot
        if not snapshot:
            return {'status': 'unavailable', 'items': []}
        items = [item.model_dump() for item in snapshot.books]
    elif catalogue in ('spotify', 'anghami'):
        from api_routes.music import discover
        from fastapi import HTTPException
        try:
            result = discover(catalogue, q, 'SA')
        except HTTPException:
            return {'status': 'unavailable', 'items': []}
        return {'status': 'unavailable' if result['source'] == 'unavailable' else 'ok',
                'items': [{'title': row['title'], 'label': row.get('artist') or catalogue} for row in result['items'][:5]]}
    elif catalogue == 'local_music':
        from services.music_library import tracks
        items = [{'title': row['title'], 'label': row.get('artist', '')} for row in tracks()]
    else:
        from services import cinema_catalog
        try:
            result = cinema_catalog.browse('movie' if catalogue == 'movies' else 'tv', query=q)
        except cinema_catalog.CatalogError:
            return {'status': 'unavailable', 'items': []}
        return {'status': 'ok', 'items': [{'title': row['title'], 'label': row['date'][:4]}
                                         for row in result['results'][:5]]}
    return {'status': 'ok', 'items': [item for item in items if all(
        term in normalized(item['title'] + ' ' + item['label']) for term in terms
    )][:5]}


@router.get('/command')
def interpret(text: str = Query(min_length=2, max_length=240)):
    action = section_command(text)
    if action:
        return {'action': action}
    search = find_request(text)
    if search:
        return {'search': {'catalogue': search[0], 'query': search[1]}}
    return {}
