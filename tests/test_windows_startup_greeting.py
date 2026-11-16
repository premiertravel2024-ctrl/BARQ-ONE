"""Regression checks for an opt-in, one-time, nonblocking Windows welcome."""
import json
import math
import sys
import wave
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest


def sample_wav():
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\0\0' * 1024)
    return buffer.getvalue()


def test_welcome_text_uses_ashraf_and_correct_consonant():
    from voice.startup_greeting import greeting_text
    result = greeting_text()
    assert 'أشرف' in result
    assert 'بَرْء' in result
    assert 'بلاء' not in result


def test_no_greeting_on_normal_app_launch(monkeypatch):
    import voice.startup_greeting as greeting
    monkeypatch.setattr(greeting.sys, 'platform', 'win32')
    assert greeting.greeting_allowed(['BARQ.exe']) is False


def test_auto_login_requires_enabled_registry_and_preference(monkeypatch):
    import voice.startup_greeting as greeting
    import voice.background_autostart as reg
    import voice.wake as wake
    monkeypatch.setattr(greeting.sys, 'platform', 'win32')
    monkeypatch.setattr(reg, 'is_enabled', lambda: True)
    monkeypatch.setattr(wake, 'wake_preferences', lambda: {'startup_greeting': True})
    assert greeting.greeting_allowed(['BARQ.exe','--background'])
    monkeypatch.setattr(reg, 'is_enabled', lambda: False)
    assert not greeting.greeting_allowed(['BARQ.exe','--background'])
    monkeypatch.setattr(reg, 'is_enabled', lambda: True)
    monkeypatch.setattr(wake, 'wake_preferences', lambda: {'startup_greeting': False})
    assert not greeting.greeting_allowed(['BARQ.exe','--background'])


def test_once_per_boot_mutes_wake_temporarily_then_restores(tmp_path,monkeypatch):
    import voice.wake as wake
    import voice.live as live
    import voice.startup_greeting as greeting
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(greeting,'boot_marker',lambda:'boot-123')
    monkeypatch.setattr(wake,'wake_preferences',lambda:{'enabled':True,'startup_greeting':True})
    calls=[]
    monkeypatch.setattr(wake,'stop_listener',lambda:calls.append('stop'))
    monkeypatch.setattr(wake,'start_listener',lambda:calls.append('start'))
    monkeypatch.setattr(live,'ACTIVE_LIVE_CALLS',0)
    monkeypatch.setattr(greeting,'_gemini_wav',lambda text:calls.append('synth') or sample_wav())
    monkeypatch.setattr(greeting,'_play_wav',lambda audio:calls.append('play') or True)
    monkeypatch.setattr(greeting,'_windows_arabic_sapi',lambda text:pytest.fail('native fallback not expected'))
    assert greeting.speak_once() is True
    assert calls==['synth','stop','play','start']
    assert greeting.speak_once() is False
    assert json.loads((tmp_path/'startup_greeting.last_boot.json').read_text())=={'boot':'boot-123'}
    assert calls==['synth','stop','play','start']


def test_disabled_does_not_speak_or_start_microphone(tmp_path,monkeypatch):
    import voice.wake as wake
    import voice.startup_greeting as greeting
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(wake,'wake_preferences',lambda:{'enabled':True,'startup_greeting':False})
    monkeypatch.setattr(wake,'stop_listener',lambda:pytest.fail('should not stop listener'))
    assert not greeting.speak_once()


def test_active_live_call_is_not_interrupted(tmp_path,monkeypatch):
    import voice.wake as wake
    import voice.live as live
    import voice.startup_greeting as greeting
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(wake,'wake_preferences',lambda:{'enabled':True,'startup_greeting':True})
    monkeypatch.setattr(live,'ACTIVE_LIVE_CALLS',1)
    monkeypatch.setattr(wake,'stop_listener',lambda:pytest.fail('must not interrupt live call'))
    assert greeting.speak_once() is False


def test_no_reenable_if_user_paused_during_playback(tmp_path,monkeypatch):
    import voice.wake as wake
    import voice.live as live
    import voice.startup_greeting as greeting
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    monkeypatch.setattr(greeting,'boot_marker',lambda:'boot-paused')
    state={'enabled':True,'startup_greeting':True}
    monkeypatch.setattr(wake,'wake_preferences',lambda:state.copy())
    monkeypatch.setattr(live,'ACTIVE_LIVE_CALLS',0)
    monkeypatch.setattr(wake,'stop_listener',lambda:None)
    monkeypatch.setattr(wake,'start_listener',lambda:pytest.fail('must respect pause'))
    monkeypatch.setattr(greeting,'_gemini_wav',lambda text:sample_wav())
    def play(_wav):
        state['enabled']=False
        return True
    monkeypatch.setattr(greeting,'_play_wav',play)
    assert greeting.speak_once()


def test_audio_validated_and_cached_in_user_data_not_program_files(monkeypatch,tmp_path):
    from voice import startup_greeting as greeting
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    assert greeting._valid_wav(sample_wav())
    assert not greeting._valid_wav(b'not-a-wave')
    assert greeting._voice_cache('test').parent==tmp_path/'cache'


def test_desktop_window_shown_starts_welcome_without_opening_live():
    root=Path(__file__).resolve().parents[1]
    desktop=(root/'desktop.py').read_text(encoding='utf-8')
    assert 'window.events.shown += maybe_greet_after_window_shown' in desktop
    assert "start_hidden='--background' in sys.argv" in desktop


def test_wake_control_remembers_greeting_preference(tmp_path,monkeypatch):
    import voice.wake as wake
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    assert wake.wake_preferences()['startup_greeting'] is True
    (tmp_path/'wake_preferences.json').write_text(json.dumps({'enabled':True,'startup_greeting':False}),encoding='utf-8')
    assert wake.wake_preferences()['startup_greeting'] is False
    assert wake.WakeControl(enabled=True,startup_greeting=False).startup_greeting is False


def test_native_arabic_fallback_used_when_cloud_unavailable(tmp_path, monkeypatch):
    import voice.wake as wake
    import voice.live as live
    import voice.startup_greeting as greeting
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(greeting, 'boot_marker', lambda: 'offline-boot')
    monkeypatch.setattr(wake, 'wake_preferences', lambda: {'enabled':False, 'startup_greeting':True})
    monkeypatch.setattr(live, 'ACTIVE_LIVE_CALLS', 0)
    monkeypatch.setattr(greeting, '_gemini_wav', lambda _text: None)
    monkeypatch.setattr(greeting, '_windows_arabic_sapi', lambda _text: True)
    assert greeting.speak_once() is True
    assert greeting.speak_once() is False


def test_greeting_no_audio_does_not_claim_success(tmp_path,monkeypatch):
    import voice.wake as wake
    import voice.live as live
    import voice.startup_greeting as greeting
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(greeting, 'boot_marker', lambda: 'missing-audio')
    monkeypatch.setattr(wake, 'wake_preferences', lambda: {'enabled':False,'startup_greeting':True})
    monkeypatch.setattr(live, 'ACTIVE_LIVE_CALLS', 0)
    monkeypatch.setattr(greeting, '_gemini_wav', lambda _text: None)
    monkeypatch.setattr(greeting, '_windows_arabic_sapi', lambda _text: False)
    assert greeting.speak_once() is False
    assert not (tmp_path/'startup_greeting.last_boot.json').exists()
