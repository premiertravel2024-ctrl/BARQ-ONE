"""Safe native wallpaper and Cloudflare integration contract tests (no desktop needed)."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cloudflare_build_matches_actual_worker_and_free_sqlite_namespace():
    cfg = json.loads((ROOT / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert cfg["name"] == "barq-one"
    assert (ROOT / cfg["main"]).is_file()
    classes = cfg["migrations"][0]["new_sqlite_classes"]
    assert {"RoomSession", "RateLimit"} == set(classes)
    assert cfg["workers_dev"] is True
    source = (ROOT / cfg["main"]).read_text(encoding="utf-8")
    assert "roomPage" in source
    assert "new Response(roomPage" in source
    assert "WebSocketPair" in source
    assert "api/rooms" in source
    assert "BARQ_RELAY_CREATE_TOKEN" not in source


def test_integrated_wallpaper_manifest_only_selected_media(monkeypatch, tmp_path):
    from services import native_wallpaper as native
    monkeypatch.setattr(native, "_folder", lambda: tmp_path)
    monkeypatch.setattr(native, "supported", lambda: True)
    monkeypatch.setattr(native, "apply", lambda ident: {"id": ident, "status": "playing"})
    gif = tmp_path / "test.gif"
    gif.write_bytes(b"GIF89a" + b"content")
    result = native.import_file(str(gif))
    assert result["status"] == "playing"
    library = native.list_wallpapers()
    assert len(library) == 1 and library[0]["title"] == "test"
    assert native._file(result["id"]) == gif.resolve()
    for unsafe in ("../test.gif", "/tmp/another-file.mp4", "", "not-a-real-id"):
        with pytest.raises(ValueError):
            native._file(unsafe)
    script = tmp_path / "unsafe.ps1"
    script.write_text("Write-Host unsafe", encoding="utf-8")
    with pytest.raises(ValueError):
        native.import_file(str(script))


def test_integrated_native_wallpaper_is_gated_by_windows_version(monkeypatch):
    from api_routes import lively
    monkeypatch.setattr(lively.sys, "platform", "win32")
    monkeypatch.setattr(lively, "windows_version", lambda: {"family": "modern"})
    monkeypatch.delenv("BARQ_WALLPAPER_LEGACY", raising=False)
    assert lively._native_enabled() is True
    monkeypatch.setenv("BARQ_WALLPAPER_LEGACY", "1")
    assert lively._native_enabled() is False


def test_windows_installer_dispatches_bundled_engine():
    desktop = (ROOT / "desktop.py").read_text(encoding="utf-8")
    source = (ROOT / "services/native_wallpaper.py").read_text(encoding="utf-8")
    build = (ROOT / "scripts/build_windows.ps1").read_text(encoding="utf-8")
    assert "--barq-wallpaper-engine" in desktop
    assert "services.native_wallpaper" in desktop
    assert "desktop.py" in build
    assert "create_window" in source and "WorkerW" in source
    assert "winget" not in source
