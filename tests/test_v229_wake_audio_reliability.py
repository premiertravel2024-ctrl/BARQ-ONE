"""Wake recognition, microphone diagnostics, and no-silent-call regressions."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_egyptian_wake_variants_and_prefix_commands():
    from scripts.barq_wake_vosk import wake_recognized
    for said in ('يا برق', 'يا بَرْء', 'يا برك', 'يا بارق', 'يا برق افتح كروم', 'يا برء سامعني', 'برق'):
        assert wake_recognized(said), said
    for unrelated in ('بلاء', 'يا بلاء', 'لواء', 'في برق بعيد', 'افتح كروم يا برق', '', 'يا بر', 'إغلاق التطبيق'):
        assert not wake_recognized(unrelated), unrelated


def test_mic_source_preference_does_not_enable_microphone(tmp_path, monkeypatch):
    from voice import wake
    from scripts import barq_wake_vosk as listener
    prefs = tmp_path/'wake_preferences.json'
    monkeypatch.setattr(wake,'wake_config_path',lambda:prefs)
    monkeypatch.setattr(listener,'STATE',tmp_path)
    app=FastAPI();app.include_router(wake.router)
    with TestClient(app) as client:
        assert listener.preferred_input_device() is None
        response=client.post('/v1/voice/wake/control',json={'enabled':False,'edge_glow':True,'input_device':5})
        assert response.status_code==200
        assert response.json()['input_device']==5
        assert listener.preferred_input_device()==5
        assert not wake.wake_preferences()['enabled']
        assert client.post('/v1/voice/wake/control',json={'enabled':False,'input_device':-1}).status_code==422
        assert listener.preferred_input_device()==5


def test_listener_status_reports_input_meter_without_audio_or_transcript(tmp_path,monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake,'wake_config_path',lambda:tmp_path/'prefs.json')
    monkeypatch.setattr(wake,'wake_log_path',lambda:tmp_path/'status.json')
    monkeypatch.setattr(wake,'_companion',None)
    (tmp_path/'status.json').write_text(json.dumps({'state':'listening','level':27,'audio_seen':True,
      'heard_speech':True,'input_device':'USB Microphone','input_devices':[{'id':2,'name':'USB Microphone'}],
      'updated':__import__('time').time()}))
    # The platform is not Win32 here: mock running status without starting audio.
    class FakeProc:
        def poll(self):return None
    monkeypatch.setattr(wake,'_companion',FakeProc())
    response=wake.wake_status()
    assert response['level']==27
    assert response['input_device_name']=='USB Microphone'
    assert response['input_devices'][0]['id']==2
    assert 'transcript' not in response and 'audio' not in response
    monkeypatch.setattr(wake,'_companion',None)


def test_live_wake_sends_one_voice_greeting_and_keeps_regular_call_untouched():
    root=Path(__file__).resolve().parents[1]
    server=(root/'voice/live.py').read_text(encoding='utf8')
    client=(root/'frontend/src/lib/liveVoice.ts').read_text(encoding='utf8')
    dialog=(root/'frontend/src/components/chat/LiveVoiceDialog.tsx').read_text(encoding='utf8')
    settings=(root/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf8')
    assert 'started_from_wake' in server and "if started_from_wake:" in server
    assert "turn_complete=True" in server
    assert "wake=${wakeGreeting?'1':'0'}" in client
    assert "autoStart);" in dialog
    assert 'input_device' in settings and 'مستوى الصوت' in settings
    assert 'بَرْء' in server and 'بلاء' in server and 'أشرف محمد' in server


def test_microphone_pcm_to_wake_dispatch_without_real_hardware(monkeypatch,tmp_path):
    """Simulate the capture callback -> recognizer partials -> authenticated wake send."""
    import sys
    from types import SimpleNamespace
    from scripts import barq_wake_vosk as wake
    monkeypatch.setattr(wake,'STATE',tmp_path)
    monkeypatch.setattr(wake,'live_active',lambda record:False)
    monkeypatch.setattr(wake,'endpoint',lambda:None)
    wake.STOP.clear();wake.PAUSED.clear()
    sent=[]
    def send():
        sent.append('wake')
        wake.STOP.set()
        return True
    monkeypatch.setattr(wake,'send_wake',send)
    class Recognition:
        def __init__(self,*args):pass
        def AcceptWaveform(self,pcm):return False
        def PartialResult(self):return json.dumps({'partial':'يا برء افتح'},ensure_ascii=False)
    class AudioStream:
        def __init__(self,**kw):self.callback=kw['callback']
        def __enter__(self):
            for _ in range(4):self.callback(b'\x04\x05'*1024,1024,None,None)
            return self
        def __exit__(self,*args):pass
    def query_devices(device=None,kind=None):
        return {'default_samplerate':16000,'name':'Fake microphone','max_input_channels':1} if kind else [{'name':'Fake microphone','max_input_channels':1}]
    monkeypatch.setitem(sys.modules,'sounddevice',SimpleNamespace(RawInputStream=AudioStream,query_devices=query_devices))
    monkeypatch.setitem(sys.modules,'vosk',SimpleNamespace(Model=lambda _:object(),KaldiRecognizer=Recognition,SetLogLevel=lambda _:None))
    icon=SimpleNamespace(title='',stop=lambda:None)
    try:
        wake.listen_loop(icon)
        assert sent==['wake']
        status=json.loads((tmp_path/'wake_status.json').read_text())
        assert status['state']=='activated'
        assert status['input_device']=='Fake microphone'
        assert status['audio_seen'] is True
    finally:wake.STOP.clear()
