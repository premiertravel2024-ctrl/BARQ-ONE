"""Offline regression gates for BARQ media/resource feature implementation.

These tests never stop a real process, open a public tunnel, or read a real
user video. Full host/guest WebRTC remains a Windows + two-browser test.
"""
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient


def test_runtime_windows_version_detection(monkeypatch):
    from core import desktop_capabilities as d
    monkeypatch.setattr(d.sys,"platform","win32")
    monkeypatch.setattr(d.sys,"getwindowsversion",lambda: SimpleNamespace(major=6,minor=3,build=9600),raising=False)
    assert d.windows_version()["family"]=="legacy"
    monkeypatch.setattr(d.sys,"getwindowsversion",lambda: SimpleNamespace(major=10,minor=0,build=22631))
    assert d.windows_version()["release"]=="11"
    monkeypatch.setattr(d.sys,"getwindowsversion",lambda: SimpleNamespace(major=10,minor=0,build=17763))
    assert d.windows_version()["family"]=="modern"


def test_resource_saver_restricts_to_known_non_critical_names():
    from services import resource_saver as saver
    classification=saver._decision
    assert classification("winlogon.exe",501,set(),False)[0]=="critical"
    assert classification("BARQ.exe",502,set(),False)[0]=="critical"
    assert classification("ffmpeg.exe",503,set(),False)[0]=="critical"
    assert classification("cloudflared.exe",504,set(),False)[0]=="critical"
    assert classification("Discord.exe",505,set(),False)[0]=="keep"
    assert classification("Spotify.exe",506,set(),True)[0]=="keep"
    assert classification("Spotify.exe",506,set(),False)[0]=="safe"
    assert classification("Spotify.exe",506,{506},False)[0]=="critical"


def test_resource_saver_never_pauses_without_explicit_approval(monkeypatch):
    from services import resource_saver as saver
    monkeypatch.setattr(saver.sys,"platform","win32")
    with pytest.raises(PermissionError):
        saver.activate("gaming",[111],confirmed=False)
    with pytest.raises(ValueError):
        saver.activate("movie",[111],confirmed=True,seconds=999)
    with pytest.raises(ValueError):
        saver.activate("unknown",[111],confirmed=True)


def test_lively_library_cannot_accept_path_traversal(monkeypatch,tmp_path):
    from api_routes import lively
    root=tmp_path/"wallpapers"
    root.mkdir()
    good=root/"wall-01"
    good.mkdir()
    (good/"LivelyInfo.json").write_text('{"Title":"Rain"}',encoding="utf-8")
    monkeypatch.setattr(lively,"_library_folder",lambda:root)
    assert [x["title"] for x in lively.items()]==["Rain"]
    assert lively._wallpaper("wall-01")==good
    from fastapi import HTTPException
    for value in ("../secret","..","/tmp/other","wall-01/../../"):
        with pytest.raises(HTTPException):
            lively._wallpaper(value)


def test_lively_controls_are_allowlisted_without_shell(monkeypatch):
    from api_routes import lively
    sent=[]
    monkeypatch.setattr(lively,"_run",lambda args: sent.append(args) or {"status":"command_sent","verified":False})
    monkeypatch.setattr(lively,"windows_version",lambda: {"family":"modern"})
    assert lively.wallpaper_action(lively.Action(action="pause"))["verified"] is False
    assert sent[-1]==["app","--play","false"]
    lively.wallpaper_action(lively.Action(action="stop"))
    assert sent[-1]==["closewp","--monitor","-1"]
    with pytest.raises(Exception):
        lively.Action(action="shell",wallpaper_id="anything")


def test_watch_link_has_one_guest_token_and_separate_code(monkeypatch):
    from services import watch_together as watch
    monkeypatch.setattr(watch,"_ensure_server",lambda:None)
    room=watch.create_room()
    assert room["status"]=="created" and not room["public"]
    assert room["guest_url"]!=room["host_url"]
    assert room["room_code"].isdigit() and len(room["room_code"])==6
    assert not room["guest_url"].endswith(room["room_code"])
    with TestClient(watch.app) as client:
        assert client.get("/r/"+room["room_id"]+"?role=guest&token=bad").status_code==403
        assert client.get("/r/"+room["room_id"]+"?role=guest&token="+room["guest_url"].split("token=")[1]).status_code==200
        assert client.get("/anything-else").status_code==404
    assert watch.close_room(room["room_id"])


def test_watch_room_chat_only_goes_to_authorized_guest(monkeypatch):
    from services import watch_together as watch
    monkeypatch.setattr(watch,"_ensure_server",lambda:None)
    info=watch.create_room()
    host_token=info["host_url"].split("token=")[1]
    guest_token=info["guest_url"].split("token=")[1]
    room_id=info["room_id"]
    host="/signal/"+room_id+"?role=host&token="+host_token
    guest="/signal/"+room_id+"?role=guest&token="+guest_token+"&code="+info["room_code"]
    with TestClient(watch.app) as client:
        with client.websocket_connect(host) as a:
            assert a.receive_json()["type"]=="ready"
            with client.websocket_connect(guest) as b:
                assert b.receive_json()["type"]=="ready"
                assert a.receive_json()["type"]=="peer-joined"
                assert b.receive_json()["type"]=="peer-joined"
                a.send_json({"type":"chat","text":"السلام عليكم"})
                assert b.receive_json()["text"]=="السلام عليكم"
                b.send_json({"type":"request-pause","value":True})
                assert a.receive_json()["type"]=="request-pause"
    watch.close_room(room_id)


def test_app_uses_same_consent_gate_for_new_feature_routes():
    import api
    # FastAPI's route-wrapper compatibility layer can expose _IncludedRouter
    # objects instead of the flattened endpoint paths on api.app.routes.
    # Inspect each actual source APIRouter and confirm integration into api.py.
    from api_routes import resource_saver, lively, watch, feature_command
    route_groups={
        "resources":resource_saver.router,
        "lively":lively.router,
        "watch":watch.router,
        "features":feature_command.router,
    }
    routes={str(getattr(route,"path",""))
            for router in route_groups.values() for route in router.routes}
    assert "/v1/resource-saver/processes" in routes
    assert "/v1/resource-saver/mode" in routes
    assert "/v1/wallpapers/action" in routes
    assert "/v1/watchrooms/start" in routes
    assert "/v1/watchrooms/publish" in routes
    assert "/v1/features/command" in routes
    source=(Path(__file__).resolve().parents[1]/"api.py").read_text(encoding="utf-8")
    for include in ("resource_saver_router","lively_router","watch_router","feature_command_router"):
        assert "app.include_router("+include+")" in source


def test_new_ui_tabs_and_voice_tool_are_real(monkeypatch):
    root=Path(__file__).resolve().parents[1]
    shell=(root/"frontend/src/pages/BarqOne.tsx").read_text(encoding="utf-8")
    for section in ("resources","wallpapers","watch"):
        assert "['"+section+"'," in shell
    voice=(root/"voice/computer_tools.py").read_text(encoding="utf-8")
    assert "'name':'barq_feature_command'" in voice
    from api_routes.feature_command import run_command
    from computer_control import api as computer_api
    from services import watch_together

    # This test must be deterministic even if the developer has already
    # enabled BARQ computer control in their real LOCALAPPDATA settings.
    # The production consent gate remains fully active.
    monkeypatch.setattr(computer_api, "load_policy",
                        lambda: SimpleNamespace(enabled=False))

    def unexpected_room_creation():
        raise AssertionError("A blocked voice command started a watch room")

    monkeypatch.setattr(watch_together, "create_room", unexpected_room_creation)
    with pytest.raises(PermissionError, match="Computer Control"):
        run_command("watch","start")
