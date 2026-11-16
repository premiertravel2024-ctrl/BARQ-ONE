"""Regression tests for conflicting old BARQ tray and spoken assistant identity."""
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_legacy_takeover_only_matches_own_installed_helper(tmp_path):
    from voice.legacy_wake import is_own_legacy_wake
    root = tmp_path / 'BARQ'
    (root / 'scripts').mkdir(parents=True)
    assert is_own_legacy_wake({'exe':str(root/'BARQ_Wake.exe'), 'cmdline':[]},root)
    assert is_own_legacy_wake({'exe':'C:/Python/python.exe', 'cmdline':['python',str(root/'scripts/barq_wake_vosk.py')]},root)
    assert not is_own_legacy_wake({'exe':str(tmp_path/'AnotherInstall/BARQ_Wake.exe'), 'cmdline':[]},root)
    assert not is_own_legacy_wake({'exe':'C:/Tools/Another.exe','cmdline':[]},root)
    assert not is_own_legacy_wake({'exe':'C:/Python/python.exe', 'cmdline':['python','C:/somewhere/app.py']},root)


def test_legacy_takeover_stops_only_verified_own_helper(tmp_path):
    from voice.legacy_wake import retire_legacy_listeners
    root = tmp_path / 'BARQ'
    own = SimpleNamespace(pid=301,info={'exe':str(root/'BARQ_Wake.exe'),'cmdline':[]})
    unrelated = SimpleNamespace(pid=302,info={'exe':str(tmp_path/'Other/BARQ_Wake.exe'),'cmdline':[]})
    observed=[]
    for proc in (own,unrelated):
        proc.terminate=lambda p=proc:observed.append(('terminate',p.pid))
        proc.wait=lambda timeout,p=proc:observed.append(('wait',p.pid,timeout))
    class FakePS:
        class NoSuchProcess(Exception):pass
        class AccessDenied(Exception):pass
        class TimeoutExpired(Exception):pass
        @staticmethod
        def process_iter(fields):return [own,unrelated]
    ok,detail=retire_legacy_listeners(root,FakePS)
    assert ok and not detail
    assert observed==[('terminate',301),('wait',301,3)]


def test_takeover_denied_if_old_companion_cannot_exit(tmp_path):
    from voice.legacy_wake import retire_legacy_listeners
    root = tmp_path / 'BARQ'
    class FakePS:
        class NoSuchProcess(Exception):pass
        class AccessDenied(Exception):pass
        class TimeoutExpired(Exception):pass
        @staticmethod
        def process_iter(fields):return [SimpleNamespace(pid=555, info={'exe':str(root/'BARQ_Wake.exe'),'cmdline':[]},
             terminate=lambda: (_ for _ in ()).throw(FakePS.AccessDenied()))]
    ok,detail=retire_legacy_listeners(root,FakePS)
    assert not ok and 'اقفل' in detail


def test_voice_identity_in_both_gemini_live_modes():
    from voice.live import live_system_instruction
    for enabled in (False,True):
        prompt=live_system_instruction(enabled)
        assert 'أشرف محمد' in prompt
        assert 'اسمك برق' in prompt
        assert 'فاكرني' in prompt
        assert 'Gemini' in prompt
    assert 'open_on_computer' in live_system_instruction(True)
    assert 'open_on_computer' not in live_system_instruction(False)


def test_restart_requires_opt_in_and_same_origin(tmp_path,monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake,'wake_config_path',lambda:tmp_path/'prefs.json')
    called=[]
    monkeypatch.setattr(wake,'restart_listener',lambda:called.append(True) or (True,'starting'))
    app=FastAPI()
    app.include_router(wake.router)
    with TestClient(app) as client:
        assert client.post('/v1/voice/wake/restart').status_code==409
        (tmp_path/'prefs.json').write_text('{"enabled":true,"edge_glow":true}')
        assert client.post('/v1/voice/wake/restart',headers={'origin':'https://evil.com'}).status_code==403
        response=client.post('/v1/voice/wake/restart')
        assert response.status_code==200 and response.json()['state']=='starting'
        assert called==[True]


def test_voice_settings_expose_restart_button():
    source=(Path(__file__).resolve().parents[1]/'frontend/src/components/layout/VoiceSettings.tsx').read_text()
    assert '/v1/voice/wake/restart' in source
    assert 'حل التعارض وإعادة تشغيل الاستماع' in source


def test_listener_takeover_occurs_before_launch(tmp_path,monkeypatch):
    from voice import wake
    calls=[]
    monkeypatch.setattr(wake,'_companion',None)
    monkeypatch.setattr(wake,'wake_executable',lambda:[str(tmp_path/'BARQ_Wake.exe'),'--headless'])
    monkeypatch.setattr(wake,'wake_log_path',lambda:tmp_path/'wake_status.json')
    monkeypatch.setattr(wake,'retire_legacy_listeners',lambda:calls.append('takeover') or (True,''))
    monkeypatch.setattr(wake,'native_dependencies_present',lambda:False)
    monkeypatch.setattr(wake,'model_path',lambda:None)
    class FakeProc:
        def poll(self):return None
    monkeypatch.setattr(wake.subprocess,'Popen',lambda *a,**kw:calls.append('launch') or FakeProc())
    try:
        assert wake.start_listener()==(True,'starting')
        assert calls==['takeover','launch']
    finally:
        monkeypatch.setattr(wake,'_companion',None)


def test_denied_takeover_does_not_start_second_listener(tmp_path,monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake,'_companion',None)
    monkeypatch.setattr(wake,'wake_executable',lambda:[str(tmp_path/'BARQ_Wake.exe'),'--headless'])
    monkeypatch.setattr(wake,'retire_legacy_listeners',lambda:(False,'close old tray'))
    monkeypatch.setattr(wake,'native_dependencies_present',lambda:False)
    monkeypatch.setattr(wake,'model_path',lambda:None)
    monkeypatch.setattr(wake.subprocess,'Popen',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('must not launch')))
    assert wake.start_listener()==(False,'close old tray')


def test_direct_mic_path_is_preferred_when_dependencies_are_present(tmp_path, monkeypatch):
    from voice import wake
    calls=[]
    monkeypatch.setattr(wake, '_companion', None)
    monkeypatch.setattr(wake, 'native_dependencies_present', lambda:True)
    monkeypatch.setattr(wake, 'model_path', lambda:tmp_path)
    monkeypatch.setattr(wake, 'retire_legacy_listeners', lambda:calls.append('takeover') or (True,''))
    monkeypatch.setattr(wake._direct_listener, 'start',lambda:calls.append('direct') or (True,'starting'))
    monkeypatch.setattr(wake.subprocess,'Popen', lambda *a,**kw: (_ for _ in ()).throw(AssertionError('legacy process must not launch')))
    assert wake.start_listener() == (True,'starting')
    assert calls == ['takeover','direct']
