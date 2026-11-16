"""Cloudflare workers.dev must not see Python's default automated client UA."""
from services import watch_together as watch


def test_cloudflare_room_creation_uses_barq_user_agent(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, max_bytes): return b'{"room_id":"mock"}'

    class Opener:
        def open(self, request, timeout):
            captured["user_agent"] = request.get_header("User-agent")
            captured["accept"] = request.get_header("Accept")
            captured["content_type"] = request.get_header("Content-type")
            captured["method"] = request.get_method()
            captured["data"] = request.data
            return Response()

    monkeypatch.setattr(watch, "build_opener", lambda *_: Opener())
    value = watch._relay_request("https://barq-one.ashraf-mohamed.workers.dev",
                                 "/api/rooms", "", method="POST", data={"mode":"video"})
    assert value == {"room_id":"mock"}
    assert captured["method"] == "POST"
    assert captured["user_agent"].startswith("BARQ-ONE/")
    assert "Python-urllib" not in captured["user_agent"]
    assert captured["accept"] == "application/json"
    assert captured["content_type"] == "application/json"
    assert captured["data"] == b'{"mode": "video"}'


def test_websocket_and_http_use_identical_application_user_agent():
    from pathlib import Path
    path=Path(watch.__file__)
    content=path.read_text(encoding="utf-8")
    assert 'user_agent_header=CLOUDFLARE_CLIENT_AGENT' in content
    assert '"User-Agent":CLOUDFLARE_CLIENT_AGENT' in content
