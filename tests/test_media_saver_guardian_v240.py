"""Watchdog regression: BARQ must never leave an optional app frozen on crash."""
import json
import sys
import types
import pytest


def test_guardian_only_resumes_exact_pid_creation_time(tmp_path,monkeypatch):
    from services import resource_saver_guardian as guardian
    path=tmp_path/"resource_saver_paused.json"
    path.write_text(json.dumps({"paused":{
        "123":{"name":"Spotify.exe","start":100.0},
        "124":{"name":"Spotify.exe","start":100.0},
    },"expires_at":0}),encoding="utf-8")
    resumed=[]
    class FakeProc:
        def __init__(self,pid):self.pid=pid
        def create_time(self):return 100.0 if self.pid==123 else 200.0
        def resume(self):resumed.append(self.pid)
    fake=types.SimpleNamespace(Process=FakeProc,NoSuchProcess=type("NoSuchProcess",(Exception,),{}),
        ZombieProcess=type("ZombieProcess",(Exception,),{}),
        AccessDenied=type("AccessDenied",(Exception,),{}))
    monkeypatch.setitem(sys.modules,"psutil",fake)
    answer=guardian.restore(path)
    assert answer["resumed"]==[123]
    assert resumed==[123]
    assert json.loads(path.read_text(encoding="utf-8"))["paused"]=={}


def test_resource_saver_fails_closed_if_guardian_cannot_start(monkeypatch):
    from services import resource_saver as saver
    class FakeProc:
        suspended=[]
        def __init__(self,pid):self.pid=pid
        def name(self):return "Spotify.exe"
        def create_time(self):return 100.0
        def suspend(self):self.suspended.append(self.pid)
        def resume(self):pass
    class FakePsutil:
        Process=FakeProc
        NoSuchProcess=type("NoSuchProcess",(Exception,),{})
        AccessDenied=type("AccessDenied",(Exception,),{})
        ZombieProcess=type("ZombieProcess",(Exception,),{})
    monkeypatch.setattr(saver.sys,"platform","win32")
    monkeypatch.setattr(saver,"_psutil",lambda:FakePsutil)
    monkeypatch.setattr(saver,"_protected_pid_set",lambda _:set())
    monkeypatch.setattr(saver,"_visible_window",lambda _:False)
    monkeypatch.setattr(saver,"_persist",lambda:True)
    monkeypatch.setattr(saver,"_start_guardian",lambda _start:(_ for _ in ()).throw(RuntimeError("guardian unavailable")))
    monkeypatch.setattr(saver,"_paused",{})
    with pytest.raises(RuntimeError,match="guardian unavailable"):
        saver.activate("gaming",[123],confirmed=True)
    assert FakeProc.suspended==[], "Must not suspend before crash guardian is ready"


def test_guardian_mode_skips_desktop_singleton_and_voice():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"desktop.py").read_text(encoding="utf-8")
    main=source[source.index("def main() -> int:"):]
    assert "if len(sys.argv)==5 and sys.argv[1]=='--resource-saver-guardian':" in main
    assert main.index("--resource-saver-guardian")<main.index("from voice.desktop_instance")
