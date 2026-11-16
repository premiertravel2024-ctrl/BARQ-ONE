"""Explicitly opted-in Windows tray wake requests, never raw desktop actions.

A companion listening process can only request activation of the existing
Gemini Live interface; tool execution remains behind BARQ's normal approvals.
"""
from __future__ import annotations

import json
import os
import secrets
import time
import subprocess
import sys
import atexit
from pathlib import Path
from threading import Lock
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from core.paths import state_file
from voice.legacy_wake import retire_legacy_listeners
from voice.direct_wake import DirectWake, native_dependencies_present, model_path
from voice.supervisor import WakeSupervisor

router = APIRouter(prefix='/v1/voice/wake', tags=['voice-wake'])
_guard = Lock()
_token = secrets.token_urlsafe(36)
_sequence = 0
_last_wake = 0.0
_companion: subprocess.Popen | None = None
_speaking_until = 0.0
_wake_handoff_until = 0.0

# New installs record directly inside BARQ.exe. The old helper is retained
# solely as a compatibility fallback while upgrading a previous installation.
def _native_wake_trigger():
    register_wake('يا برق', _token)
    from voice.background_window import show_on_wake
    show_on_wake()

def _live_session_running():
    from voice.live import ACTIVE_LIVE_CALLS
    return ACTIVE_LIVE_CALLS > 0 or time.monotonic() < _wake_handoff_until

def _chosen_input_device():
    return wake_preferences()['input_device']

_direct_listener = DirectWake(_native_wake_trigger, _live_session_running, _chosen_input_device)


_supervisor = WakeSupervisor(
    enabled=lambda: wake_preferences()['enabled'],
    status=lambda: wake_status(),
    restart=lambda: restart_listener(),
    live_active=_live_session_running,
)

def run_wake_supervisor(stop, interval=5):
    _supervisor.run(stop, interval)

def wake_supervisor_status() -> dict:
    return _supervisor.snapshot()

def wake_config_path() -> Path:
    return state_file('wake_preferences.json')

def wake_log_path() -> Path:
    return state_file('wake_status.json')

def wake_preferences() -> dict:
    try:
        stored = json.loads(wake_config_path().read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        stored = {}
    chosen=stored.get('input_device')
    return {'show_on_wake':stored.get('show_on_wake') is True,'enabled': stored.get('enabled') is True,
            'edge_glow': stored.get('edge_glow', True) is not False,
            'startup_greeting': stored.get('startup_greeting', True) is not False,
            'wake_computer_enabled': stored.get('wake_computer_enabled') is True,
            'input_device': chosen if type(chosen) is int and 0 <= chosen <= 255 else None}

def set_wake_enabled_from_tray(enabled: bool) -> None:
    """Persist explicit tray choice; never start listening by accident."""
    preferences = wake_preferences()
    preferences['enabled'] = bool(enabled)
    if enabled:
        from services import personal_assistant as personal
        with personal._lock:
            saved=personal.read();saved['paused']=False;personal.write(saved)
    target = wake_config_path()
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(preferences), encoding='utf-8')
    temp.replace(target)


def wake_executable() -> list[str] | None:
    if sys.platform != 'win32':
        return None
    if getattr(sys, 'frozen', False):
        exe = Path(sys.executable).resolve().parent / 'BARQ_Wake.exe'
        return [str(exe), '--headless'] if exe.is_file() else None
    source = Path(__file__).resolve().parents[1] / 'scripts' / 'barq_wake_vosk.py'
    return [sys.executable, str(source), '--headless'] if source.is_file() else None

def stop_listener() -> None:
    global _companion
    _direct_listener.stop()
    with _guard:
        proc, _companion = _companion, None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

def start_listener() -> tuple[bool, str]:
    """Start an opt-in listener, taking over a verified legacy helper first."""
    global _companion
    with _guard:
        if _companion is not None and _companion.poll() is None:
            return True, 'running'
        args = wake_executable()
        direct_ready = native_dependencies_present() and model_path() is not None
        from voice.owner_voice import enrolled
        if not direct_ready and enrolled():return False, 'تمييز صوتك يحتاج المستمع الداخلي؛ أصلح مكونات الصوت بدل المستمع القديم'
        if not direct_ready and not args:
            return False, 'Wake model/runtime unavailable; reinstall the voice component from BARQ Setup'
        # Older tray helpers share our named mutex, even after updating BARQ.
        # Retire ONLY the exact BARQ_Wake.exe/script from THIS installation.
        ok, explanation = retire_legacy_listeners()
        if not ok:
            return False, explanation
        # Use a direct microphone stream in BARQ.exe when available.
        # Do not start a second helper process in the normal installed build.
        if direct_ready:
            return _direct_listener.start()
        # The previous standalone helper remains a legacy fallback only.
        # Do not report an obsolete error written by the previous tray after
        # a successful takeover while the new helper is loading its model.
        try:
            wake_log_path().unlink(missing_ok=True)
        except OSError:
            pass
        try:
            kwargs = {'cwd': str(Path(args[0]).resolve().parent), 'stdin': subprocess.DEVNULL,
                      'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
            if sys.platform == 'win32':
                kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            _companion = subprocess.Popen(args, **kwargs)
            return True, 'starting'
        except OSError as exc:
            return False, f'Cannot start wake engine: {exc}'


def restart_listener() -> tuple[bool, str]:
    """Used by the visible BARQ settings, not remotely or by voice."""
    stop_listener()
    if _direct_listener.status()['running']:
        return False, 'الميكروفون القديم لسه بيقفل؛ حاول بعد لحظة'
    return start_listener()


def initialize_desktop_listener() -> None:
    if wake_preferences()['enabled']:
        start_listener()

def wake_status() -> dict:
    pref = wake_preferences()
    with _guard:
        running = _companion is not None and _companion.poll() is None
    native = _direct_listener.status()
    if native['running'] or native['state'] in ('error', 'stopping'):
        # The live engine reports its human-readable device name as
        # "input_device".  The control API, however, uses "input_device" as
        # the persisted integer PortAudio index.  Never let display-only
        # engine telemetry overwrite the API's numeric preference: toggling
        # another checkbox would otherwise post a string and fail with 422.
        return {**native, **pref, 'supervisor': wake_supervisor_status(), 'model_installed': model_path() is not None,
                'platform_supported': sys.platform == 'win32',
                'input_device_name': native.get('input_device', '')}
    model = (Path(sys.executable).resolve().parent if getattr(sys,'frozen',False)
             else Path(__file__).resolve().parents[1]) / 'models' / 'wake' / 'vosk-model-ar-mgb2-0.4'
    try:
        info = json.loads(wake_log_path().read_text(encoding='utf-8'))
        if not isinstance(info,dict) or time.time() - float(info.get('updated',0)) > 12:
            info = {'state':'stopped' if not running else 'starting', 'detail':'No recent microphone status'}
    except (OSError, ValueError, TypeError):
        info = {'state':'starting' if running else 'stopped', 'detail':''}
    # Preserve a recent failure even if the helper has already exited.
    failed = info.get('state') == 'error'
    legacy = state_file('wake_models') / 'vosk-model-ar-mgb2-0.4'
    return {**pref, 'supervisor': wake_supervisor_status(), 'running':running, 'state':info.get('state','unknown') if running or failed else 'stopped',
            'detail':info.get('detail','') if running or failed else '', 'last_wake':info.get('last_wake',0),
            'model_installed': ((model/'am').is_dir() and (model/'conf').is_dir()) or ((legacy/'am').is_dir() and (legacy/'conf').is_dir()),
            'platform_supported':sys.platform=='win32',
            'level':info.get('level',0), 'audio_seen':info.get('audio_seen',False),
            'input_device_name':info.get('input_device',''),
            'input_devices':info.get('input_devices',[]),
            'last_audio_at':info.get('last_audio_at',0),
            'heard_speech':info.get('heard_speech',False),
            'last_recognized':'', 'engine':'legacy'}

class WakeControl(BaseModel):
    show_on_wake:bool=False
    enabled: bool
    edge_glow: bool = True
    wake_computer_enabled: bool = False
    input_device: int | None = Field(default=None, ge=0, le=255)
    start_with_windows: bool = False
    startup_greeting: bool = True

class SpeakingSignal(BaseModel):
    active: bool

def _same_origin(request: Request) -> None:
    # Restrict state changes to the local webview. Hostile websites must not
    # be able to enable an always-on microphone using a cross-origin POST.
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Same-origin BARQ window required')
    if request.headers.get('sec-fetch-site','same-origin') not in ('same-origin','none'):
        raise HTTPException(403, 'Cross-site request denied')

@router.get('/control')
def read_control():
    from voice.background_autostart import is_enabled
    return {**wake_status(), 'start_with_windows': is_enabled()}

@router.post('/control')
def update_control(body: WakeControl, request: Request):
    _same_origin(request)
    from voice.background_autostart import supported, configure, is_enabled
    if body.start_with_windows != is_enabled():
        if not supported():
            raise HTTPException(409, 'Autostart is supported only by the installed Windows BARQ')
        try:
            configure(body.start_with_windows)
        except OSError as exc:
            raise HTTPException(500, 'Could not update Windows startup permission') from exc
    # Store before launching; the assistant does not auto-enable by default.
    old = wake_preferences()
    target = wake_config_path()
    tmp = target.with_suffix('.tmp')
    tmp.write_text(json.dumps(body.model_dump()), encoding='utf-8')
    tmp.replace(target)
    if body.enabled:
        ok, message = (restart_listener() if old['input_device'] != body.input_device else start_listener())
        if not ok:
            return {**wake_status(), 'state':'error', 'detail':message}
    else:
        stop_listener()
    return {**wake_status(), 'start_with_windows': is_enabled()}

@router.post('/restart')
def restart_wake(request: Request):
    _same_origin(request)
    if not wake_preferences()['enabled']:
        raise HTTPException(409,'Enable background listening first')
    ok, detail = restart_listener()
    if not ok:
        return {**wake_status(), 'state':'error', 'detail':detail}
    return {**wake_status(), 'state':'starting', 'detail':'إعادة تشغيل الاستماع داخل برق...'}

@router.post('/enroll')
def enroll_wake(request: Request):
    """Explicit opt-in, 3 samples; store spectral templates, never raw audio."""
    _same_origin(request)
    if not wake_preferences()['enabled']:
        raise HTTPException(409,'Enable background listening first')
    ok, message = _direct_listener.begin_enrollment()
    if not ok: raise HTTPException(409,message)
    return {'started': True, 'detail': message}

@router.post('/enroll/cancel')
def cancel_wake_enrollment(request: Request):
    _same_origin(request)
    _direct_listener.cancel_enrollment()
    return {'ok':True}

@router.delete('/enroll')
def delete_wake_enrollment(request: Request):
    _same_origin(request)
    _direct_listener.delete_profile()
    return {'ok':True}

@router.post('/test')
def test_wake(request: Request):
    _same_origin(request)
    if not wake_preferences()['enabled']:
        raise HTTPException(409,'Enable background listening first')
    sequence = register_wake('يا برق', _token)
    return {'queued':True, 'sequence':sequence}

@router.post('/handoff')
def handoff_microphone_to_live(request: Request):
    """Stop *this app's* opt-in wake listener before Live captures the mic.

    Does not change the user's saved wake preference. The supervisor resumes
    listening after the Live session ends. Same-origin local UI only.
    """
    global _wake_handoff_until
    _same_origin(request)
    with _guard:
        _wake_handoff_until = time.monotonic() + 30
    stop_listener()
    return {'ok': True, 'wake_suspended': True}


@router.post('/speaking')
def update_speaking(body: SpeakingSignal, request: Request):
    global _speaking_until
    _same_origin(request)
    # A renderer crash cannot leave the red border stuck on.
    with _guard:
        _speaking_until = time.monotonic() + 3 if body.active else 0
    return {'ok':True}

def is_speaking() -> bool:
    with _guard:
        return wake_preferences()['edge_glow'] and time.monotonic() < _speaking_until

atexit.register(stop_listener)


class WakeSignal(BaseModel):
    phrase: str = Field(min_length=2, max_length=80)


def discovery_file() -> Path:
    return state_file('wake_endpoint.json')


def publish_endpoint(port: int) -> None:
    """Only the current desktop instance advertises a short-lived bearer token."""
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    file = discovery_file()
    temp = file.with_suffix('.tmp')
    try:
        temp.write_text(json.dumps({'port': port, 'token': _token, 'pid': os.getpid()}), encoding='utf-8')
        os.chmod(temp, 0o600)
        os.replace(temp, file)
    finally:
        temp.unlink(missing_ok=True)


def clear_endpoint() -> None:
    """Don't delete a discovery record installed by a newer BARQ process."""
    file = discovery_file()
    try:
        record = json.loads(file.read_text(encoding='utf-8'))
        if record.get('token') == _token and record.get('pid') == os.getpid():
            file.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError):
        pass


def register_wake(phrase: str, token: str) -> int:
    global _sequence, _last_wake, _wake_handoff_until
    if not isinstance(token, str) or not secrets.compare_digest(token, _token):
        raise PermissionError('Wake companion authorization required')
    # The companion must detect a wake phrase; arbitrary text is not a trigger.
    simplified = phrase.strip().lower()
    if simplified not in ('يا برق', 'برق', 'barq', 'hey barq', 'hey bark'):
        raise ValueError('Wake phrase not recognized')
    with _guard:
        now = time.monotonic()
        if now - _last_wake >= 2:
            _sequence += 1
            _last_wake = now
            # Hold the local wake stream while browser permission and Gemini
            # handshake are starting. Avoid racing for the same microphone.
            _wake_handoff_until = now + 25
        return _sequence


@router.post('/trigger')
def wake_trigger(body: WakeSignal, x_barq_wake_token: str = Header(default='')):
    try:
        seq = register_wake(body.phrase, x_barq_wake_token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from voice.background_window import show_on_wake
    show_on_wake()
    return {'queued': True, 'sequence': seq}


@router.post('/show')
def show_desktop_instance(x_barq_wake_token: str = Header(default='')):
    # Only the already-running BARQ process knows this random local token.
    if not secrets.compare_digest(x_barq_wake_token, _token):
        raise HTTPException(403, 'BARQ instance token required')
    from voice.background_window import show_on_wake
    show_on_wake()
    return {'ok': True}


@router.get('/pending')
def wake_pending(since: int = 0):
    # Only same-origin renderer may observe the pending request. Event is
    # ephemeral: restarting the app or waiting 30 seconds invalidates it.
    with _guard:
        fresh = _last_wake > 0 and time.monotonic() - _last_wake < 30
        return {'sequence': _sequence, 'wake': fresh and _sequence > max(0, since),
                'computer_enabled': wake_preferences()['wake_computer_enabled']}


@router.get('/session')
def live_session_status():
    from voice.live import ACTIVE_LIVE_CALLS
    return {'live_active': ACTIVE_LIVE_CALLS > 0}
