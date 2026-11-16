"""Regression for Pydantic 422 on enabling wake-computer access while recording."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    from voice import wake
    app = FastAPI()
    app.include_router(wake.router)
    return TestClient(app)


def _direct_state(name='Microphone Array (Intel Smart Sound)'):
    return {'running': True, 'state': 'listening', 'detail': '', 'input_device': name,
            'input_devices': [{'id': 7, 'name': name}], 'level': 14,
            'engine': 'direct', 'last_wake': 0}


def test_status_separates_portaudio_id_from_display_name(monkeypatch, tmp_path):
    from voice import wake
    monkeypatch.setattr(wake, 'wake_config_path', lambda:tmp_path/'preferences.json')
    monkeypatch.setattr(wake._direct_listener, 'status', lambda: _direct_state())
    monkeypatch.setattr(wake, 'model_path', lambda:None)
    (tmp_path/'preferences.json').write_text('{"enabled":true,"input_device":7}',encoding='utf-8')
    with _client() as client:
        data=client.get('/v1/voice/wake/control').json()
    assert data['input_device'] == 7
    assert type(data['input_device']) is int
    assert data['input_device_name'] == 'Microphone Array (Intel Smart Sound)'
    assert data['input_devices'][0]['id'] == 7
    assert data['enabled'] is True


def test_default_mic_control_never_returns_name_as_index(monkeypatch,tmp_path):
    from voice import wake
    monkeypatch.setattr(wake, 'wake_config_path', lambda:tmp_path/'preferences.json')
    monkeypatch.setattr(wake._direct_listener, 'status', lambda: _direct_state())
    monkeypatch.setattr(wake, 'model_path', lambda:None)
    with _client() as client:
        data=client.get('/v1/voice/wake/control').json()
    assert data['input_device'] is None
    assert data['input_device_name'] == 'Microphone Array (Intel Smart Sound)'


def test_toggle_computer_access_roundtrip_preserves_mic_selection(monkeypatch,tmp_path):
    from voice import wake
    monkeypatch.setattr(wake, 'wake_config_path', lambda:tmp_path/'preferences.json')
    monkeypatch.setattr(wake._direct_listener, 'status', lambda: _direct_state())
    monkeypatch.setattr(wake,'model_path', lambda:None)
    monkeypatch.setattr(wake,'start_listener',lambda:(True,'running'))
    monkeypatch.setattr(wake,'restart_listener',lambda:(True,'running'))
    with _client() as client:
        response=client.post('/v1/voice/wake/control',json={
            'enabled': True, 'edge_glow': True, 'input_device': 7,
            'wake_computer_enabled': False})
        assert response.status_code == 200
        body={key:response.json()[key] for key in (
            'enabled','edge_glow','input_device','wake_computer_enabled','start_with_windows','startup_greeting')}
        body['wake_computer_enabled']=True
        result=client.post('/v1/voice/wake/control',json=body)
        assert result.status_code == 200, result.text
        assert result.json()['wake_computer_enabled'] is True
        assert result.json()['input_device'] == 7
        assert result.json()['input_device_name'] == 'Microphone Array (Intel Smart Sound)'
    assert wake.wake_preferences()['input_device'] == 7


def test_voice_settings_defensively_reject_legacy_device_names():
    root=Path(__file__).resolve().parents[1]
    src=(root/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    assert "typeof wake.input_device==='number'" in src
    assert "typeof wake?.input_device==='number'" in src
    assert 'Number.isInteger(wake.input_device)' in src
