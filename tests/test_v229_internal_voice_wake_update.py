"""Regression gates for wake listener, no second tray app, glow and in-place update."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

def client_for(router):
    app=FastAPI()
    app.include_router(router)
    return TestClient(app)

ROOT = Path(__file__).resolve().parents[1]


def test_wake_variants_and_does_not_accept_conversation():
    from scripts.barq_wake_vosk import is_arabic_wake
    for phrase in ('يا برق', 'برق', 'يا برك', 'يا بارق'):
        assert is_arabic_wake(phrase)
    for phrase in ('', 'امسح الملفات', 'يا برق افتح المتصفح', 'كيف تعمل اليوم يا برق أنا هنا'):
        assert not is_arabic_wake(phrase)


def test_glow_covers_the_screen_edges_and_no_invalid_dims():
    from voice.screen_glow import edge_rectangles
    assert edge_rectangles(0,0,1920,1080,10) == ((0,0,1920,10),(0,1070,1920,10),
                                                 (0,10,10,1060),(1910,10,10,1060))
    assert edge_rectangles(-1920,0,3840,1080,8)[0] == (-1920,0,3840,8)
    assert not edge_rectangles(0,0,0,100,10)


def test_microphone_defaults_to_off_and_edge_glow_can_be_disabled(tmp_path, monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake,'wake_config_path',lambda:tmp_path/'prefs.json')
    assert not wake.wake_preferences()['enabled']
    assert wake.wake_preferences()['edge_glow']
    with client_for(wake.router) as client:
        response=client.post('/v1/voice/wake/control',json={'enabled':False,'edge_glow':False})
        assert response.status_code==200
        assert response.json()['edge_glow'] is False
        assert client.get('/v1/voice/wake/control').json()['enabled'] is False
        assert client.post('/v1/voice/wake/test').status_code == 409


def test_cross_site_requests_cannot_activate_microphone(tmp_path,monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake,'wake_config_path',lambda:tmp_path/'prefs.json')
    with client_for(wake.router) as client:
        response=client.post('/v1/voice/wake/control',json={'enabled':True},
                             headers={'origin':'https://malicious.example'})
        assert response.status_code==403
        assert not (tmp_path/'prefs.json').exists()


def test_wake_test_dispatch_and_speaking_lease(tmp_path,monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake,'wake_config_path',lambda:tmp_path/'prefs.json')
    (tmp_path/'prefs.json').write_text(json.dumps({'enabled':True,'edge_glow':True}))
    with client_for(wake.router) as client:
        before=client.get('/v1/voice/wake/pending').json()['sequence']
        fired=client.post('/v1/voice/wake/test')
        assert fired.status_code==200
        assert fired.json()['sequence']>=before
        assert client.post('/v1/voice/wake/speaking',json={'active':True}).status_code==200
        assert wake.is_speaking()
        assert client.post('/v1/voice/wake/speaking',json={'active':False}).status_code==200
        assert not wake.is_speaking()


def test_listener_helper_has_headless_no_tray_path_and_diag():
    source=(ROOT/'scripts/barq_wake_vosk.py').read_text()
    assert 'def headless(' in source and '--headless' in source
    assert "report('listening'" in source and 'PartialResult()' in source
    assert 'audioop.ratecv' in source


def test_ui_receives_wake_globally_and_glow_follows_playback():
    app=(ROOT/'frontend/src/App.tsx').read_text()
    voice=(ROOT/'frontend/src/lib/liveVoice.ts').read_text()
    settings=(ROOT/'frontend/src/components/layout/VoiceSettings.tsx').read_text()
    assert '/v1/voice/wake/pending' in app
    assert 'setPlayground(false)' in app
    assert '<WorkspaceStudio' not in app
    assert 'reportSpeaking(true)' in voice and 'reportSpeaking(false)' in voice
    assert '/v1/voice/wake/control' in settings
    assert 'جلو نبيتي على حواف شاشات' in settings


def test_update_preserves_app_id_and_skips_vosk_model():
    original=(ROOT/'scripts/installer.iss').read_text()
    updater=(ROOT/'scripts/installer_update.iss').read_text()
    assert '9BB70D04-1EC5-4BC6-B811-64B08F5C8977' in original
    assert '9BB70D04-1EC5-4BC6-B811-64B08F5C8977' in updater
    assert 'models\\wake' not in updater
    assert 'UninstallDelete' not in updater
    assert 'BARQ_Update_' in updater
