"""OpenHub catalog and a serialized, user-authorized WinGet queue."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from queue import Queue
from threading import Lock, Thread
from time import time
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from core.paths import resource, state_file
from core.processes import background_options
from core.security import child_env
from core.tool_locator import find_tool
from api_routes.openhub_tools import download_source, network_allowed
from api_routes.openhub_descriptions import DESCRIPTIONS

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/v1/openhub', tags=['openhub'])
_queue = Queue()
_worker = None
_lock = Lock()
_initialized = set()
_inventory: dict[str, str] = {}
_inventory_lock = Lock()
_scan_lock = Lock()
_inventory_checked = False


@lru_cache(maxsize=1)
def catalog():
    rows = {}
    for line in resource('config', 'openhub.tsv').read_text(encoding='utf-8').splitlines():
        name, category, repo, *package = line.split('\t')
        info = DESCRIPTIONS.get(repo.casefold(), {})
        rows[repo.casefold()] = {
            'id': repo.casefold(), 'name': name, 'category': category,
            'repository': repo, 'url': f'https://github.com/{repo}',
            'description_ar': info.get('ar', ''),
            'description_en': info.get('en', ''),
            'package': package[0] if package else None,
            'setup': repo.casefold() in {'cursortouch/windows-mcp', 'librehardwaremonitor/librehardwaremonitor'},
        }
    return rows


def winget():
    return find_tool('winget.exe') if sys.platform == 'win32' else None


def run_winget(command, args, timeout):
    return subprocess.run([command, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=timeout, encoding='utf-8', errors='replace', env=child_env(), **background_options())


def inventory(command):
    with tempfile.TemporaryDirectory(prefix='barq-openhub-') as folder:
        output = Path(folder) / 'installed.json'
        run = run_winget(command, ['export', '-o', str(output), '--include-versions',
                                   '--accept-source-agreements', '--disable-interactivity'], 45)
        if run.returncode != 0 or not output.is_file():
            raise ValueError('WinGet could not read the installed package inventory.')
        return {item['PackageIdentifier'].casefold(): item.get('Version') or ''
                for source in json.loads(output.read_text(encoding='utf-8-sig')).get('Sources', [])
                for item in source.get('Packages', []) if 'PackageIdentifier' in item}


@contextmanager
def connect():
    path = state_file('openhub.sqlite3')
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        if path not in _initialized:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, item TEXT, action TEXT, status TEXT,
                    detail TEXT, created REAL)""")
                db.execute("UPDATE jobs SET status='interrupted' WHERE status IN ('queued','running')")
            _initialized.add(path)
        with db:
            yield db
    finally:
        db.close()


def job_status(job_id, status, detail=''):
    with _lock, connect() as db:
        db.execute('UPDATE jobs SET status=?,detail=? WHERE id=?', (status, detail[:450], job_id))


def update_inventory(command):
    global _inventory_checked
    with _scan_lock:
        packages = inventory(command)
        visible = {key: packages[key] for row in catalog().values() if row['package']
                   if (key := row['package'].casefold()) in packages}
        with _inventory_lock:
            _inventory.clear()
            _inventory.update(visible)
            _inventory_checked = True
    return visible


def run_job(job_id, command, package, action, previous):
    job_status(job_id, 'running')
    if not network_allowed():
        job_status(job_id, 'failed', 'Local-only mode blocks downloads.')
        return
    if action == 'source':
        try:
            destination = state_file('openhub-downloads') / job_id
            destination.mkdir(parents=True, exist_ok=False)
            archive = download_source(catalog()[package]['repository'], destination)
        except (OSError, ValueError, ImportError, httpx.HTTPError):
            job_status(job_id, 'failed', 'The official source ZIP could not be downloaded.')
        else:
            job_status(job_id, 'verified', str(archive))
        return
    if action == 'setup' and package == 'librehardwaremonitor/librehardwaremonitor':
        from core.hardware_sensors import ensure_sensors_ready
        status = ensure_sensors_ready()
        if status == 'installed':
            job_status(job_id, 'verified', 'LibreHardwareMonitor installed. Sensor access is checked separately in System Monitor.')
        else:
            job_status(job_id, 'needs_review' if status == 'timeout' else 'failed',
                       'Sensor setup: ' + status + '. See sensor-install.log.')
        return
    if action == 'setup':
        try:
            uv = find_tool('uv.exe')
            if not uv:
                if not command:
                    raise OSError('WinGet unavailable')
                flags = ['--id','astral-sh.uv','--exact','--source','winget','--accept-source-agreements',
                         '--accept-package-agreements','--disable-interactivity','--no-upgrade']
                if run_winget(command, ['install', *flags], 120).returncode:
                    raise OSError('uv install failed')
                uv = find_tool('uv.exe')
            if not uv:
                raise OSError('uv not detected')
            result = run_winget(uv, ['--no-config','tool','install','--python','3.14',
                                    '--default-index','https://pypi.org/simple','windows-mcp==0.8.8'], 420)
            if result.returncode or not find_tool('windows-mcp.exe'):
                raise OSError('Windows-MCP not detected')
        except subprocess.TimeoutExpired:
            job_status(job_id, 'needs_review', 'Windows-MCP setup timed out.')
        except OSError:
            job_status(job_id, 'failed', 'Windows-MCP setup could not be verified.')
        else:
            job_status(job_id, 'verified', 'Windows-MCP 0.8.8')
        return
    flags = ['--id', package, '--exact', '--source', 'winget',
             '--accept-source-agreements', '--disable-interactivity']
    try:
        match = run_winget(command, ['show', *flags], 30)
        if match.returncode:
            job_status(job_id, 'failed', 'Exact package not resolved by the WinGet community source.')
            return
        if action == 'download':
            destination = state_file('openhub-downloads') / job_id
            destination.mkdir(parents=True, exist_ok=False)
            download = run_winget(command, ['download', *flags, '--accept-package-agreements',
                                            '--download-directory', str(destination)], 600)
            if download.returncode:
                job_status(job_id, 'failed', f'WinGet exit 0x{download.returncode & 0xffffffff:08X}.')
            elif any(file.is_file() and file.suffix.casefold() in {'.exe','.msi','.msix','.msixbundle','.zip','.appx','.appxbundle'}
                     for file in destination.rglob('*')):
                job_status(job_id, 'verified', str(destination))
            else:
                job_status(job_id, 'needs_review', 'WinGet returned no recognized installer file.')
            return
        extra = ['--no-upgrade'] if action == 'install' else []
        install = run_winget(command, [action, *flags, '--accept-package-agreements', *extra], 600)
        if install.returncode:
            job_status(job_id, 'failed', f'WinGet exit 0x{install.returncode & 0xffffffff:08X}.')
            return
    except subprocess.TimeoutExpired:
        job_status(job_id, 'needs_review', 'WinGet timed out. Check Windows before retrying.')
        return
    except (OSError, ValueError):
        job_status(job_id, 'failed', 'WinGet could not complete the action.')
        return
    try:
        version = update_inventory(command).get(package.casefold())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        version = None
    if not version or action == 'upgrade' and version == previous:
        job_status(job_id, 'needs_review', 'WinGet finished. The installed version was not verified.')
    else:
        job_status(job_id, 'verified', version)


def drain_jobs():
    while True:
        args = _queue.get()
        try:
            run_job(*args)
        except Exception:
            logger.exception('OpenHub worker could not update a job')
        finally:
            _queue.task_done()


def submit_jobs(jobs):
    global _worker
    with _lock:
        if not jobs:
            return
        for args in jobs:
            _queue.put_nowait(args)
        if _worker is None or not _worker.is_alive():
            _worker = Thread(target=drain_jobs, name='openhub', daemon=True)
            _worker.start()


class QueueRequest(BaseModel):
    items: list[str] = Field(min_length=1, max_length=10)
    action: str = Field(pattern='^(install|upgrade|download|source|setup)$')
    confirmed: bool = False


@router.get('/catalog')
def get_catalog():
    return {'items': list(catalog().values()), 'winget': bool(winget()), 'can_setup': sys.platform == 'win32' and bool(winget() or find_tool('uv.exe')), 'can_sensors': sys.platform == 'win32'}


@router.get('/jobs')
def get_jobs():
    with _lock, connect() as db:
        return {'jobs': [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 50')]}


@router.get('/installed')
def get_installed():
    from core.hardware_sensors import _monitor_executable
    setups = {}
    if sys.platform == 'win32':
        if _monitor_executable():
            setups['librehardwaremonitor/librehardwaremonitor'] = 'Installed locally'
        if find_tool('windows-mcp.exe'):
            setups['cursortouch/windows-mcp'] = 'Installed locally'
    with _inventory_lock:
        return {'packages': dict(_inventory), 'setups': setups, 'checked': _inventory_checked}


@router.post('/installed/refresh')
def refresh_installed():
    command = winget()
    if not command:
        raise HTTPException(503, 'WinGet is unavailable.')
    try:
        update_inventory(command)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(503, 'WinGet could not refresh the installed inventory.') from exc
    return get_installed()


@router.post('/jobs', status_code=202)
def enqueue(req: QueueRequest):
    if not req.confirmed:
        raise HTTPException(403, 'Confirm the package selection in OpenHub first.')
    if not network_allowed():
        raise HTTPException(403, 'Local-only mode blocks package downloads.')
    source = req.action == 'source'
    setup = req.action == 'setup'
    command = None if source else winget()
    sensors = setup and req.items == ['librehardwaremonitor/librehardwaremonitor']
    if setup:
        if sys.platform != 'win32' or not (sensors or command or find_tool('uv.exe')):
            raise HTTPException(503, 'Windows-MCP setup requires Windows and uv or WinGet.')
    elif not source and not command:
        raise HTTPException(503, 'WinGet is unavailable.')
    rows = [catalog().get(key) for key in dict.fromkeys(req.items)]
    if any(not item or (setup and not item['setup']) or (not (source or setup) and not item['package']) for item in rows):
        raise HTTPException(400, 'The selected actions are unavailable for at least one entry.')
    installed = get_installed()['packages']
    created = []
    with _lock, connect() as db:
        active = {row['item'] for row in db.execute("SELECT item FROM jobs WHERE status IN ('queued','running')")}
        if len(active | set(req.items)) > 20:
            raise HTTPException(409, 'OpenHub queue is full.')
        eligible = [row for row in rows if row['id'] not in active
                    and not (req.action == 'install' and row['package'].casefold() in installed)]
        if any(req.action == 'upgrade' and not installed.get(row['package'].casefold()) for row in eligible):
            raise HTTPException(409, 'Refresh installed versions before upgrading.')
        for row in eligible:
            job_id = uuid4().hex
            db.execute('INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?)',
                       (job_id, row['id'], req.action, 'queued', '', time()))
            created.append((job_id, row['id'] if source or setup else row['package']))
    submit_jobs([(job_id, command, package, req.action, installed.get(package.casefold()))
                 for job_id, package in created])
    return {'queued': [job_id for job_id, _ in created]}


@router.get('/details')
def details(item: str):
    row = catalog().get(item)
    if not row:
        raise HTTPException(404, 'OpenHub entry not found.')
    from os import getenv
    if getenv('LOCAL_ONLY', '').lower() in {'yes', 'true', '1'}:
        raise HTTPException(403, 'Local-only mode is active.')
    url = 'https://api.github.com/repos/' + row['repository']
    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            metadata = client.get(url)
            metadata.raise_for_status()
            release = client.get(url + '/releases/latest')
            latest = release.json().get('tag_name') if release.is_success else None
        info = metadata.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, 'Could not verify upstream metadata.') from exc
    return {'description': info.get('description'), 'license': (info.get('license') or {}).get('spdx_id'),
            'latest': latest, 'archived': bool(info.get('archived')), 'source': row['url']}


@router.get('/cpu-temperature')
def cpu_temperature():
    """Single, read-only CPU sensor call for immediate text and voice replies.

    This never invokes an LLM, starts a desktop task, runs an installer or
    returns an invented CPU temperature. The LHM localhost HTTP channel is
    attempted first; the verified DLL and WMI readers remain fallbacks.
    """
    from core.hardware_sensors import read_local_temperatures
    measured = read_local_temperatures()
    return {
        'cpu_c': measured.get('cpu_c'),
        'cpu_sensor': measured.get('cpu_sensor'),
        'provider': measured.get('provider'),
        'measured_at': measured.get('measured_at'),
        'reason': measured.get('reason'),
    }


@router.get('/monitor')
def monitor():
    from core.adaptive_resources import resources
    from core.hardware_sensors import snapshot, read_nvidia_gpu
    try:
        disk = shutil.disk_usage(state_file('openhub.sqlite3').anchor)
    except OSError:
        disk = None
    sensors = snapshot()
    if sensors.get('gpu_load_percent') is None and sensors.get('gpu_c') is not None:
        sensors['gpu_load_percent'] = read_nvidia_gpu().get('gpu_load_percent')
    processes = None
    try:
        import psutil
        measured = [entry.info for entry in psutil.process_iter(['name','memory_info'])
                    if entry.info.get('memory_info') is not None]
        ordered = sorted(measured, key=lambda entry: entry['memory_info'].rss, reverse=True)
        processes = [{'name': entry.get('name') or '—', 'rss': entry['memory_info'].rss} for entry in ordered[:8]]
    except (ImportError, OSError):
        pass
    return {'measured_at': time(), 'hardware': resources.snapshot(include_gpu=True), 'sensors': sensors, 'processes': processes,
            'disk_percent': round(disk.used * 100 / disk.total, 1) if disk and disk.total else None}


@router.get('/runtime')
def runtime():
    """Read local tool presence without starting any service or running packages."""
    from importlib.util import find_spec
    from core.tool_locator import hardware_monitor_folder
    from voice.readiness import report

    modules = {
        'Open WebUI': 'open_webui', 'Open Interpreter': 'interpreter',
        'OpenHands': 'openhands', 'Browser Use': 'browser_use',
        'LangGraph': 'langgraph', 'Silero VAD': 'silero_vad',
        'faster-whisper': 'faster_whisper',
    }
    tools = [{'name': name, 'detected': find_spec(module) is not None} for name, module in modules.items()]
    tools.extend([
        {'name': 'Ollama', 'detected': bool(find_tool('ollama'))},
        {'name': 'Windows-MCP', 'detected': bool(find_tool('windows-mcp'))},
        {'name': 'llama.cpp', 'detected': bool(shutil.which('llama-cli'))},
        {'name': 'LibreHardwareMonitor', 'detected': bool(hardware_monitor_folder())},
    ])
    return {'tools': tools, 'local_stt_ready': report()['local_stt_ready']}

@router.post('/monitor/fps')
def measure_fps():
    from services.game_performance import capture_fps
    return capture_fps()


@router.get('/jobs/{job_id}/file')
def downloaded_file(job_id: str):
    from fastapi.responses import FileResponse
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise HTTPException(404, 'Download not found.')
    with _lock, connect() as db:
        row = db.execute("SELECT action, status, detail FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row or row['action'] != 'source' or row['status'] != 'verified':
        raise HTTPException(404, 'Download not found.')
    root = (state_file('openhub-downloads') / job_id).resolve()
    archive = Path(row['detail']).resolve()
    if archive.parent != root or archive.suffix != '.zip' or not archive.is_file():
        raise HTTPException(404, 'Download file no longer exists.')
    return FileResponse(archive, filename=archive.name, media_type='application/zip')


@router.post('/jobs/{job_id}/folder')
def show_download(job_id: str):
    if sys.platform != 'win32' or not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise HTTPException(404, 'Download not found.')
    with _lock, connect() as db:
        exists = db.execute("SELECT 1 FROM jobs WHERE id=? AND status='verified' AND action IN ('source','download')", (job_id,)).fetchone()
    folder = state_file('openhub-downloads') / job_id
    if not exists or not folder.is_dir() or folder.is_symlink():
        raise HTTPException(404, 'Download folder no longer exists.')
    os.startfile(str(folder))
    return {'opened': True}


@router.post('/monitor/elevate')
def elevate_sensor_provider():
    """Explicit UI action: Windows asks for approval; never elevate BARQ itself."""
    from core.hardware_sensors import _monitor_executable
    if sys.platform != 'win32':
        raise HTTPException(503, 'Sensor access requires Windows.')
    executable = _monitor_executable()
    if not executable:
        raise HTTPException(409, 'Install the sensor provider first.')
    import ctypes
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                              ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
    shell_execute.restype = ctypes.c_void_p
    result = shell_execute(None, 'runas', str(executable), None, str(executable.parent), 1)
    if not result or result <= 32:
        raise HTTPException(409, 'Windows did not approve starting the sensor provider.')
    return {'status': 'requested', 'message': 'تم إرسال طلب تشغيل الحساسات لويندوز. هنعرض الحرارة لما القراءة توصل.'}
