"""Trusted catalog acquisitions and build prerequisites."""
import os
import re
import zipfile
from time import monotonic, sleep

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.paths import state_file
from core.tool_locator import find_tool
from voice.intent import command_text

router = APIRouter(prefix='/v1/openhub', tags=['openhub'])
LIMIT = 175 * 1024 * 1024


def network_allowed():
    return os.getenv('LOCAL_ONLY', '').strip().lower() not in {'yes', 'true', '1'}


def download_source(repository, destination):
    deadline = monotonic() + 180
    with httpx.Client(timeout=12, follow_redirects=False) as client:
        commit = client.get(f'https://api.github.com/repos/{repository}/commits/HEAD')
        commit.raise_for_status()
        sha = commit.json().get('sha', '')
        if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha):
            raise ValueError('GitHub did not resolve a commit')
        staged = destination / 'source.part'
        try:
            with client.stream('GET', f'https://codeload.github.com/{repository}/zip/{sha}') as response:
                response.raise_for_status()
                received = 0
                with staged.open('xb') as handle:
                    for chunk in response.iter_bytes(65536):
                        received += len(chunk)
                        if received > LIMIT or monotonic() > deadline:
                            raise ValueError('Source archive exceeds the download limit')
                        handle.write(chunk)
            if not zipfile.is_zipfile(staged):
                raise ValueError('Invalid source ZIP')
            archive = destination / f"{repository.split('/')[-1]}-{sha[:12]}.zip"
            staged.replace(archive)
            return archive
        finally:
            staged.unlink(missing_ok=True)


def requested_tool(text):
    from api_routes.openhub import catalog
    match = re.fullmatch(r'(ثبت|سطب|نزل|حمل|حمللي|نزللي|ثبتلي|install|download) (?:(?:ال)?اداه |(?:ال)?اداة |(?:ال)?برنامج |tool )?(.{1,80})', command_text(text))
    if match:
        for key, row in catalog().items():
            if match[2] in {command_text(row['name']), command_text(row['package'] or '')}:
                return key, 'setup' if row['setup'] else 'install'
    return None


class CommandRequest(BaseModel):
    text: str = Field(max_length=420)


@router.post('/command')
def tool_command(req: CommandRequest):
    from api_routes.openhub import QueueRequest, catalog, enqueue
    if not (intent := requested_tool(req.text)):
        return {'matched': False}
    key, action = intent
    row = catalog()[key]
    name = row['name']
    if action == 'install' and row['setup']:
        action = 'setup'
    if action == 'install' and not row['package']:
        return {'matched': True, 'status': 'unavailable', 'message': f'{name} موجود في المكتبة، لكن لسه ملوش وصفة تثبيت جاهزة في برق. ملفات المصدر متاحة من التفاصيل؛ تنزيلها لوحده مش تثبيت.'}
    try:
        queued = enqueue(QueueRequest(items=[key], action=action, confirmed=True))['queued']
    except HTTPException:
        return {'matched': True, 'status': 'unavailable', 'message': f'تعذّر تجهيز {name}. راجع توفر WinGet أو وضع العمل المحلي.'}
    return {'matched': True, 'status': 'queued' if queued else 'already_queued',
            'message': (f'ضفت {name} لطابور التنزيل والتثبيت من داخل برق. هتلاقي النتيجة في طابور التثبيت؛ مش هاعتبره مثبّت إلا بعد التحقق.' if queued
                        else f'{name} موجود عندك أو ليه طلب شغال في OpenHub.')}


class AutoToolsSetting(BaseModel):
    enabled: bool


@router.get('/auto-tools')
def read_auto_tools():
    try:
        enabled = state_file('openhub-auto-tools.txt').read_text(encoding='utf-8') == 'enabled'
    except OSError:
        enabled = False
    return {'enabled': enabled}


@router.post('/auto-tools')
def write_auto_tools(setting: AutoToolsSetting):
    from api_routes.openhub import _lock
    with _lock:
        path = state_file('openhub-auto-tools.txt')
        staged = path.with_suffix('.part')
        staged.write_text('enabled' if setting.enabled else 'disabled', encoding='utf-8')
        staged.replace(path)
    return read_auto_tools()


def ensure_build_tool(executable, item):
    from api_routes.openhub import QueueRequest, _lock, connect, enqueue, winget
    if found := find_tool(executable):
        return found
    if not (read_auto_tools()['enabled'] and network_allowed() and winget()):
        return None
    try:
        enqueue(QueueRequest(items=[item], action='install', confirmed=True))
    except HTTPException:
        return None
    deadline = monotonic() + 420
    while monotonic() < deadline:
        if found := find_tool(executable):
            return found
        with _lock, connect() as db:
            current = db.execute("SELECT status FROM jobs WHERE item=? AND action='install' ORDER BY created DESC LIMIT 1", (item,)).fetchone()
        if not current or current['status'] not in {'running','queued'}:
            break
        sleep(1)
    return find_tool(executable)
