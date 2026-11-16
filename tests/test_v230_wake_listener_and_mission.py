"""Wake activation is local, consent-based, and does not execute tools."""
import json
import pytest
from fastapi.testclient import TestClient
from voice import wake


def test_wake_secret_and_phrase_required():
    with TestClient(__import__('api').app) as client:
        assert client.post('/v1/voice/wake/trigger', json={'phrase':'يا برق'}).status_code == 403
        assert client.post('/v1/voice/wake/trigger', headers={'X-BARQ-WAKE-TOKEN':'bad'}, json={'phrase':'يا برق'}).status_code == 403
        assert client.post('/v1/voice/wake/trigger', headers={'X-BARQ-WAKE-TOKEN':wake._token}, json={'phrase':'امسح الملفات'}).status_code == 400
        before = client.get('/v1/voice/wake/pending?since=999999').json()
        assert before['wake'] is False
        ok = client.post('/v1/voice/wake/trigger', headers={'X-BARQ-WAKE-TOKEN':wake._token}, json={'phrase':'يا برق'})
        assert ok.status_code == 200
        seq=ok.json()['sequence']
        assert seq > 0
        assert client.get('/v1/voice/wake/pending', params={'since':seq-1}).json()['wake'] is True
        assert client.get('/v1/voice/wake/pending', params={'since':seq}).json()['wake'] is False
        assert client.get('/v1/voice/wake/session').json() == {'live_active':False}


def test_wake_endpoint_is_only_exported_to_local_state(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path))
    wake.publish_endpoint(12234)
    record=json.loads(wake.discovery_file().read_text(encoding='utf-8'))
    assert record['port']==12234 and record['token']==wake._token
    assert 'http://' not in wake.discovery_file().read_text(encoding='utf-8')
    wake.clear_endpoint()
    assert not wake.discovery_file().exists()


def test_wake_ttl_prevents_stale_auto_calls(monkeypatch):
    monkeypatch.setattr(wake,'_last_wake',__import__('time').monotonic()-50)
    assert wake.wake_pending(0)['wake'] is False


def test_source_companion_opt_in_files_are_present():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    assert 'SpeechRecognized' in (root/'scripts/barq_wake_tray.ps1').read_text(encoding='utf-8-sig')
    assert 'START_BARQ_WAKE.vbs' in (root/'START_BARQ_WAKE.bat').read_text(encoding='ascii')
    assert 'scripts\\barq_wake_tray.ps1' not in (root/'START_BARQ_WAKE.bat').read_text(encoding='ascii')
    assert 'AUTO' not in (root/'scripts/barq_wake_tray.ps1').read_text(encoding='utf-8-sig').splitlines()[0]


def test_arabic_wake_detector_is_word_bound_and_ignores_long_utterances():
    from scripts.barq_wake_vosk import is_arabic_wake
    assert is_arabic_wake('يا برق')
    assert is_arabic_wake('برق')
    assert is_arabic_wake('يا بَرْق')
    assert not is_arabic_wake('البرق في السماء')
    assert not is_arabic_wake('حابب أشوف فيلم عن برق يا ترى هنلاقيه')
    assert not is_arabic_wake('امسح الملفات')


def test_mission_lookup_recovers_only_exact_existing_goal(tmp_path, monkeypatch):
    from mission.tracking import start
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    workspace=tmp_path/'work'
    (workspace/'existing').mkdir(parents=True)
    start(str(workspace),'existing','desktop_python','ابني برنامج مدير ملفات',['main.py'])
    with TestClient(__import__('api').app) as client:
        ok=client.post('/v1/agent/mission-lookup',json={'workspace':str(workspace),'goal':'ابني برنامج مدير ملفات'})
        assert ok.status_code==200 and ok.json()['project']=='existing'
        unknown=client.post('/v1/agent/mission-lookup',json={'workspace':str(workspace),'goal':'ابني برنامج آخر'})
        assert unknown.status_code==404
