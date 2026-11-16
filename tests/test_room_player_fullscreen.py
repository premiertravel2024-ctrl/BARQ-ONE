"""BARQ media rooms: fullscreen, responsive UI, and guest/host parity."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _player_page() -> str:
    text = (ROOT / "services/watch_web.py").read_text(encoding="utf-8")
    match = re.search(r'PAGE = r"""([\s\S]*?)"""', text)
    assert match is not None
    return match.group(1)


def test_local_and_cloud_rooms_have_identical_player_ui():
    cloud = (ROOT / "cloudflare/room.html").read_text(encoding="utf-8")
    assert _player_page() == cloud


def test_fullscreen_expands_stage_with_fit_and_cover_options():
    page = _player_page()
    assert 'id="videoStage"' in page
    assert 'id="enterFullscreen"' in page
    assert 'id="fitMode"' in page
    assert "stage.requestFullscreen()" in page
    assert "document.exitFullscreen()" in page
    assert "document.fullscreenElement" in page
    assert 'data-fit="contain"' in page
    assert '[data-fit="cover"]' in page
    assert '.player:fullscreen' in page
    assert 'object-fit:contain' in page
    assert 'object-fit:cover' in page
    assert "fullscreenchange" in page


def test_music_room_hides_video_only_fullscreen_options():
    page = _player_page()
    assert "document.getElementById('screenActions').hidden=true;" in page
    assert "document.body.classList.add('room-music')" in page
    assert 'id="fileName"' in page
    assert 'id="subFileName"' in page


def test_embedded_windows_room_grants_iframe_fullscreen_permission():
    react = (ROOT / "frontend/src/pages/WatchTogether.tsx").read_text(encoding="utf-8")
    assert 'allowFullScreen' in react
    assert 'allow="autoplay; encrypted-media; fullscreen; picture-in-picture"' in react
    assert 'barq-watch-hero' in react
    assert 'barq-watch-player' in react
    css = (ROOT / "frontend/src/pages/barqMedia.css").read_text(encoding="utf-8")
    assert '.barq-watch-player iframe' in css
