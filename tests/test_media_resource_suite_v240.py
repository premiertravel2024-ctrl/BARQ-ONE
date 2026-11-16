"""BARQ new-feature safety and isolated watch signaling integration tests."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def test_process_saver_protects_windows_barq_and_open_windows():
    from services import resource_saver as saver
    for name in ("csrss.exe","winlogon.exe","explorer.exe","MsMpEng.exe",
                 "BARQ.exe","lively.exe","ffmpeg.exe","cloudflared.exe"):
        risk,_=saver._decision(name,100,set(),False)
        assert risk=="critical",name
    assert saver._decision("spotify.exe",100,set(),True)[0]=="keep"
    assert saver._decision("unknown-service.exe",100,set(),False)[0]=="keep"
    assert saver._decision("Spotify.exe",100,{100},False)[0]=="critical"
    assert saver._decision("Spotify.exe",100,set(),False)[0]=="safe"


def test_resource_saver_never_pauses_without_explicit_approval(monkeypatch):
    from services import resource_saver as saver
    monkeypatch.setattr(saver.sys,"platform","win32")
    with pytest.raises(PermissionError):
        saver.activate("gaming",[123],confirmed=False)


def test_platform_detection_no_false_windows_81(monkeypatch):
    from core import desktop_capabilities as capabilities
    class Version:
        major=6
        minor=3
        build=9600
    monkeypatch.setattr(capabilities.sys,"platform","win32")
    monkeypatch.setattr(capabilities.sys,"getwindowsversion",lambda:Version(),raising=False)
    old=capabilities.windows_version()
    assert old["family"]=="legacy" and old["release"]=="8.1"
    Version.major,Version.minor,Version.build=10,0,22631
    modern=capabilities.windows_version()
    assert modern["family"]=="modern" and modern["release"]=="11"


def test_lively_action_does_not_run_arbitrary_shell(monkeypatch):
    from api_routes import lively
    calls=[]
    monkeypatch.setattr(lively,"_run",lambda args:calls.append(args) or {"status":"command_sent","verified":False})
    result=lively.wallpaper_action(lively.Action(action="pause"))
    assert result["verified"] is False
    assert calls==[["app","--play","false"]]
    result=lively.wallpaper_action(lively.Action(action="stop"))
    assert calls[-1]==["closewp","--monitor","-1"]


def test_watch_room_token_unauthorized_pages_and_no_files(monkeypatch):
    from services import watch_together as watch
    monkeypatch.setattr(watch,"_ensure_server",lambda:None)
    room=watch.create_room()
    room_id=room["room_id"]
    with TestClient(watch.app) as client:
        assert client.get("/r/"+room_id+"?role=guest&token=invalid").status_code==403
        assert client.get("/r/"+room_id+"?role=guest&token="+
                          watch._rooms[room_id].guest_token).status_code==200
        assert client.get("/C:/Users/Public/Documents/secret.txt").status_code==404
        assert client.get("/v1/computer/status").status_code==404
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/signal/"+room_id+"?role=guest&token="+watch._rooms[room_id].guest_token+
                "&code=000000") as ws:
                ws.receive_json()
    assert watch.close_room(room_id)
    assert watch._find(room_id) is None


def test_watch_room_websocket_signaling_and_ephemeral_chat(monkeypatch):
    from services import watch_together as watch
    monkeypatch.setattr(watch,"_ensure_server",lambda:None)
    room=watch.create_room()
    r=watch._rooms[room["room_id"]]
    host_path=f"/signal/{r.id}?role=host&token={r.host_token}"
    guest_path=f"/signal/{r.id}?role=guest&token={r.guest_token}&code={r.code}"
    try:
        with TestClient(watch.app) as client:
            with client.websocket_connect(host_path) as host:
                assert host.receive_json()["type"]=="ready"
                with client.websocket_connect(guest_path) as guest:
                    assert guest.receive_json()["type"]=="ready"
                    assert host.receive_json()["type"]=="peer-joined"
                    assert guest.receive_json()["type"]=="peer-joined"
                    guest.send_json({"type":"chat","text":"أهلا"})
                    message=host.receive_json()
                    assert message["type"]=="chat" and message["text"]=="أهلا"
                    host.send_json({"type":"offer","value":{"type":"offer","sdp":"fake-local-test-sdp"}})
                    value=guest.receive_json()
                    assert value["type"]=="offer" and value["value"]["type"]=="offer"
                    host.send_json({"type":"subtitle","value":"ترجمة عربية سليمة"})
                    subtitle=guest.receive_json()
                    assert subtitle["type"]=="subtitle"
                    assert subtitle["value"]=="ترجمة عربية سليمة"
    finally:
        watch.close_room(r.id)
    assert not watch.status()


def test_feature_command_watch_does_not_publish_public_room(monkeypatch):
    from api_routes import feature_command
    from services import watch_together as watch
    from computer_control import api as controls
    monkeypatch.setattr(controls,"load_policy",lambda:type("Policy",(),{"enabled":True})())
    monkeypatch.setattr(watch,"_ensure_server",lambda:None)
    try:
        result=feature_command.run_command("watch","start")
        assert result["status"]=="ready_local"
        # Voice/chat responses can later be forwarded to external AI models.
        # The room URL and authorization code MUST remain in the local UI.
        assert "result" not in result
        current=watch.active_room()
        assert current is not None
        assert current["public"] is False
        assert current["host_url"].startswith("http://127.0.0.1:")
        assert current["room_code"].isdigit()
        assert current["host_url"] not in str(result)
        assert current["guest_url"] not in str(result)
        assert current["room_code"] not in str(result)
        outcome=feature_command.run_command("watch","close")
        assert outcome["status"]=="ok"
        assert watch.active_room() is None
    finally:
        for current in watch.status():
            watch.close_room(current["room_id"])


def test_lively_local_file_import_requires_native_user_selection(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    from api_routes import lively
    sample=tmp_path/"sample.gif"
    sample.write_bytes(b"GIF89a")
    class DummyRoot:
        def withdraw(self):pass
        def attributes(self,*args):pass
        def destroy(self):pass
    selected={"value":str(sample)}
    dialog=SimpleNamespace(askopenfilename=lambda **kwargs:selected["value"])
    monkeypatch.setitem(sys.modules,"tkinter",SimpleNamespace(Tk=DummyRoot,filedialog=dialog))
    monkeypatch.setattr(lively,"_consent",lambda:None)
    invoked=[]
    monkeypatch.setattr(lively,"_run",lambda args:invoked.append(args) or {"status":"command_sent","verified":False})
    assert lively.pick_local_wallpaper()["status"]=="command_sent"
    assert invoked==[["setwp","--file",str(sample)]]
    selected["value"]=str(tmp_path/"unsafe.ps1")
    with pytest.raises(Exception):
        lively.pick_local_wallpaper()
    assert len(invoked)==1
