"""Fast, no-microphone regression gates for acoustic wake and consent."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def sample(notes, duration=.9, amp=.24):
    import numpy as np
    rate=16000
    t=np.arange(int(rate*duration)) / rate
    data=np.zeros(len(t),np.float32)
    for i,frequency in enumerate(notes):
        lo=len(t)*i//len(notes)
        hi=len(t)*(i+1)//len(notes)
        tt=t[lo:hi]
        data[lo:hi]=amp*np.sin(2*np.pi*frequency*tt)+amp*.3*np.sin(2*np.pi*2*frequency*tt)
    data*=np.clip(np.arange(len(t))/300,0,1)*np.clip((len(t)-np.arange(len(t)))/300,0,1)
    return (data*32767).astype('<i2').tobytes()


def templates():
    from voice.wake_fingerprint import signature
    return [signature(sample([350,480,390],.91)),signature(sample([355,490,395],.94)),signature(sample([345,475,385],.96))]


def test_enrolled_word_matches_without_vosk_arabic_transcript():
    from voice.wake_fingerprint import matches, threshold
    saved=templates()
    assert .61 <= threshold(saved) <= .83
    assert matches(sample([352,485,393],1.0),saved)[0]
    assert not matches(sample([950,1050,800],1.0),saved)[0]


def test_profile_is_features_not_raw_audio(tmp_path):
    from voice.wake_fingerprint import save,load
    path=tmp_path/'profile.npz'
    assert load(path)==[]
    save(path,templates())
    saved=load(path)
    assert len(saved)==3 and saved[0].shape==(36,13)
    assert path.stat().st_size < 100_000
    assert b'RIFF' not in path.read_bytes()
    path.unlink()
    assert load(path)==[]


def test_opt_in_enrollment_does_not_execute_tools_or_start_calls(tmp_path,monkeypatch):
    from voice.direct_wake import DirectWake
    import voice.wake_fingerprint as fp
    import voice.direct_wake as dw
    listener=DirectWake(lambda:pytest.fail('Enrollment must not activate Live'),lambda:False,lambda:None)
    listener.thread=SimpleNamespace(is_alive=lambda:True)
    monkeypatch.setattr(listener,'_templates_path',lambda:tmp_path/'profile.npz')
    ok,_=listener.begin_enrollment()
    assert ok
    for i in range(3):
        listener._enroll_sample(sample([350+i*3,480+i*3,390+i*3],duration=.92+i*.01))
    assert listener.has_profile()
    assert not listener.status()['enrollment_active']
    assert listener.status()['enrollment_count']==3
    listener.delete_profile()
    assert not listener.has_profile()


def test_wake_routes_only_local_call_and_requires_opt_in(tmp_path,monkeypatch):
    from voice import wake
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    config=tmp_path/'preferences.json'
    monkeypatch.setattr(wake,'wake_config_path',lambda:config)
    app=FastAPI();app.include_router(wake.router)
    with TestClient(app) as client:
        assert client.post('/v1/voice/wake/enroll').status_code==409
        assert client.post('/v1/voice/wake/enroll',headers={'Origin':'https://evil.example'}).status_code==403
        assert client.delete('/v1/voice/wake/enroll',headers={'Origin':'https://evil.example'}).status_code==403


def test_handoff_pauses_stream_before_gemini_websocket_is_ready(monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake,'_wake_handoff_until',0.0)
    monkeypatch.setattr(wake,'_last_wake',0.0)
    seq=wake.register_wake('يا برق',wake._token)
    assert seq > 0
    assert wake._live_session_running()
    assert wake._wake_handoff_until > __import__('time').monotonic()


def test_fast_ui_shortcut_and_enrollment_controls_present():
    root=Path(__file__).resolve().parents[1]
    settings=(root/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf8')
    app=(root/'frontend/src/App.tsx').read_text(encoding='utf8')
    assert '/v1/voice/wake/enroll' in settings and 'enrollment_count' in settings
    assert 'e.ctrlKey&&e.altKey' in app
