"""One-time welcome after an opted-in Windows login auto-start.

Not a Live call: this speaks a short greeting and then BARQ returns to its
local wake listener. No microphone is enabled by the greeting itself.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import wave
from io import BytesIO

from core.paths import data_dir, state_file

_lock = threading.Lock()
_started = False


def greeting_text() -> str:
    """Keep the spoken name explicit; never synthesize a personal conversation."""
    from datetime import datetime
    hour = datetime.now().hour
    intro = 'صباح الفل' if 5 <= hour < 12 else 'مسا الفل' if 12 <= hour < 22 else 'يا مساء السعادة'
    from services.personal_assistant import read
    name=read()['owner_name']
    return f'{intro} يا {name}! أنا بَرْء، موجود معاك وجاهز نبدأ.'


def boot_marker() -> str:
    """Stable for this Windows boot so restarting BARQ doesn't greet repeatedly."""
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        elapsed = ctypes.windll.kernel32.GetTickCount64() / 1000.0
        return f'boot-{int((time.time() - elapsed) // 120)}'
    return f'nonwindows-{int(time.time() // 86400)}'


def greeting_allowed(argv: list[str] | None = None) -> bool:
    if sys.platform != 'win32' or '--background' not in (argv if argv is not None else sys.argv):
        return False
    from voice.background_autostart import is_enabled
    from voice.wake import wake_preferences
    return is_enabled() and wake_preferences().get('startup_greeting', True)


def _log(status: str) -> None:
    # No audio data or API keys are logged.
    try:
        log = data_dir() / 'logs' / 'startup_greeting.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('a', encoding='utf-8') as stream:
            stream.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + status[:150] + '\n')
    except OSError:
        pass


def _valid_wav(audio: bytes) -> bool:
    try:
        with wave.open(BytesIO(audio), 'rb') as reader:
            return reader.getnframes() > 0 and reader.getnchannels() in (1, 2) and reader.getsampwidth() in (1, 2, 3, 4)
    except (EOFError, ValueError, wave.Error):
        return False


def _voice_cache(text: str) -> Path:
    digest = hashlib.sha256(('Charon:' + text).encode('utf-8')).hexdigest()[:20]
    return data_dir() / 'cache' / ('startup_welcome_' + digest + '.wav')


def _gemini_wav(text: str) -> bytes | None:
    """Use the existing user-configured voice; cache a short greeting for offline reuse."""
    from voice.gemini import gemini_key, synthesize_speech
    cached = _voice_cache(text)
    try:
        if cached.is_file() and cached.stat().st_size < 2_000_000:
            payload = cached.read_bytes()
            if _valid_wav(payload):
                return payload
    except OSError:
        pass
    if not gemini_key() or os.getenv('LOCAL_ONLY', '').lower() in ('1', 'true', 'yes'):
        return None
    try:
        wav, _ = asyncio.run(asyncio.wait_for(synthesize_speech(text, voice='Charon'), timeout=16))
        if not _valid_wav(wav) or len(wav) > 2_000_000:
            return None
        cached.parent.mkdir(parents=True, exist_ok=True)
        temp = cached.with_suffix('.tmp')
        temp.write_bytes(wav)
        temp.replace(cached)
        return wav
    except Exception as exc:
        _log('Gemini audio unavailable: ' + type(exc).__name__)
        return None


def _play_wav(wav: bytes) -> bool:
    import winsound
    try:
        winsound.PlaySound(wav, winsound.SND_MEMORY | winsound.SND_SYNC | winsound.SND_NODEFAULT)
        return True
    except RuntimeError:
        return False


def _windows_arabic_sapi(text: str) -> bool:
    """Offline fallback, only if an Arabic voice exists on this Windows account."""
    encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
    script = (
        '$ErrorActionPreference = "Stop"; '
        'Add-Type -AssemblyName System.Speech; '
        '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
        '$v = @($s.GetInstalledVoices() | Where-Object { '
        '$_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq "ar" }); '
        'if ($v.Count -lt 1) { exit 10 }; '
        '$s.SelectVoice($v[0].VoiceInfo.Name); '
        f'$t = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("{encoded}")); '
        '$s.Speak($t); exit 0'
    )
    command = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    try:
        proc = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15, check=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def speak_once() -> bool:
    """Do not speak twice per boot or interrupt an active voice session."""
    from voice.wake import wake_preferences, stop_listener, start_listener
    import voice.live as live
    if not wake_preferences().get('startup_greeting', True):
        return False
    marker = state_file('startup_greeting.last_boot.json')
    boot = boot_marker()
    try:
        last = json.loads(marker.read_text(encoding='utf-8'))
        if isinstance(last, dict) and last.get('boot') == boot:
            return False
    except (OSError, ValueError, TypeError):
        pass
    if live.ACTIVE_LIVE_CALLS:
        return False
    # Resolve cloud speech (or its cached WAV) BEFORE releasing the mic. The
    # wake supervisor can otherwise restart the listener during network delay.
    message = greeting_text()
    wav = _gemini_wav(message)
    if live.ACTIVE_LIVE_CALLS or not wake_preferences().get('startup_greeting', True):
        return False
    listener_enabled = wake_preferences()['enabled']
    if listener_enabled:
        stop_listener()  # Do not trigger BARQ with its own greeting.
    greeted = False
    try:
        greeted = (_play_wav(wav) if wav is not None else False) or _windows_arabic_sapi(message)
        if greeted:
            marker.write_text(json.dumps({'boot': boot}), encoding='utf-8')
            _log('welcome played')
        else:
            _log('welcome not played: no available Arabic speech output')
    finally:
        # Never re-enable a listener that the user switched off during playback.
        if listener_enabled and wake_preferences()['enabled'] and not live.ACTIVE_LIVE_CALLS:
            time.sleep(0.2)  # Let speaker echo settle before listening again.
            start_listener()
    return greeted


def maybe_greet_after_window_shown() -> None:
    """Nonblocking event hook; triggered only for an opt-in login auto-start."""
    global _started
    if not greeting_allowed():
        return
    with _lock:
        if _started:
            return
        _started = True

    def worker():
        time.sleep(1.5)  # Give the desktop audio endpoint time to initialize.
        try:
            speak_once()
        except Exception as exc:
            _log('welcome failed: ' + type(exc).__name__)

    threading.Thread(target=worker, name='BARQ-Login-Welcome', daemon=True).start()
