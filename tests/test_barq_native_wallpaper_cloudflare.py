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


def test_native_wallpaper_remove_only_manifest_and_never_original_file(monkeypatch, tmp_path):
    from services import native_wallpaper as native
    monkeypatch.setattr(native, "_folder", lambda: tmp_path)
    monkeypatch.setattr(native, "supported", lambda: True)
    monkeypatch.setattr(native, "apply", lambda ident: {"status": "playing", "verified": True})
    media = tmp_path / "my-cinema.gif"
    media.write_bytes(b"GIF89a" + b"wallpaper")
    native.import_file(str(media))
    identifier = native.list_wallpapers()[0]["id"]
    monkeypatch.setattr(native, "state", lambda: {"wallpaper_id": identifier})
    stopped = []
    monkeypatch.setattr(native, "stop", lambda: stopped.append(True))
    response = native.remove_wallpaper(identifier)
    assert response["status"] == "removed"
    assert response["media_deleted"] is False
    assert stopped == [True]
    assert native.list_wallpapers() == []
    assert media.exists(), "User's original wallpaper must never be deleted"
    with pytest.raises(ValueError):
        native.remove_wallpaper("../unsafe")


def test_remove_route_dispatches_only_native_records(monkeypatch):
    from api_routes import lively
    from services import native_wallpaper as native
    monkeypatch.setattr(lively, "_consent", lambda: None)
    monkeypatch.setattr(lively, "_native_enabled", lambda: True)
    monkeypatch.setattr(native, "remove_wallpaper", lambda key: {"status": "removed", "removed_id": key})
    assert lively.remove_wallpaper("a" * 24)["status"] == "removed"
    monkeypatch.setattr(lively, "_native_enabled", lambda: False)
    with pytest.raises(Exception) as exc:
        lively.remove_wallpaper("a" * 24)
    assert getattr(exc.value, "status_code", None) == 501


def test_native_wallpaper_publishes_when_loaded_and_attached_irrespective_of_order():
    source = (ROOT / "services/native_wallpaper.py").read_text(encoding="utf-8")
    assert "loaded = threading.Event()" in source
    assert "publish_when_ready()" in source
    assert "ready.is_set() or not loaded.is_set()" in source
    assert "w.events.loaded += signal_loaded" in source
    assert "w.events.before_show += attach" in source


def test_wallpaper_status_announces_safe_removal_capability(monkeypatch):
    from api_routes import lively
    from services import native_wallpaper as native
    monkeypatch.setattr(lively, "_native_enabled", lambda: True)
    monkeypatch.setattr(lively, "windows_version", lambda: {"family": "modern"})
    monkeypatch.setattr(native, "state", lambda: {"running": False, "supported": True})
    monkeypatch.setattr(native, "list_wallpapers", lambda: [])
    monkeypatch.setattr("core.desktop_capabilities.status", lambda: {"windows": {"family": "modern"}, "lively": {"installed": False}})
    response = lively.wallpaper_status(metrics=False)
    assert response["features"]["remove_wallpaper"] is True
    assert response["features"]["native_engine_handshake"] == 2


def test_native_wallpaper_previews_do_not_need_computer_control(monkeypatch, tmp_path):
    """Existing user-imported preview can render while device actions are disabled."""
    from api_routes import lively
    from services import native_wallpaper as native
    monkeypatch.setattr(lively, "_native_enabled", lambda: True)
    monkeypatch.setattr(lively, "_consent", lambda: (_ for _ in ()).throw(RuntimeError("No action permission")))
    monkeypatch.setattr(native, "_folder", lambda: tmp_path)
    media = tmp_path / "preview.gif"
    media.write_bytes(b"GIF89a" + b"animation")
    identifier = "b" * 24
    native._save({identifier: {"path": str(media), "title": "preview"}})
    response = lively.wallpaper_preview(identifier)
    assert Path(response.path) == media
    # Deleting or applying wallpapers still performs action authorization.
    with pytest.raises(RuntimeError, match="No action permission"):
        lively.remove_wallpaper(identifier)


def test_native_wallpaper_cards_show_media_preview_and_explicit_remove():
    source = (ROOT / "frontend/src/pages/Wallpapers.tsx").read_text(encoding="utf-8")
    style = (ROOT / "frontend/src/pages/wallpaperGallery.css").read_text(encoding="utf-8")
    assert 'onLoadedMetadata=' in source
    assert 'onLoadedData=' in source
    assert 'onClick={()=>setDeleteTarget(item)}' in source
    assert "data.features?.remove_wallpaper" in source
    assert 'grid-template-columns:repeat(auto-fit' in style
