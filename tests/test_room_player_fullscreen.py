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


def test_fullscreen_uses_one_icon_and_fills_stage():
    page = _player_page()
    assert 'id="videoStage"' in page
    assert 'id="enterFullscreen"' in page
    assert 'id="fitMode"' not in page
    assert "stage.requestFullscreen()" in page
    assert "document.exitFullscreen()" in page
    assert "document.fullscreenElement" in page
    assert '.player:fullscreen' in page
    assert 'object-fit:cover' in page
    assert "fullscreenchange" in page


def test_music_room_hides_video_only_fullscreen_options():
    page = _player_page()
    assert "document.getElementById('screenActions').hidden=true;" in page
    assert "document.getElementById('waitingOverlay').hidden=true;" in page
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


def test_theater_viewer_uses_full_size_stage_and_clear_media_waiting_state():
    page = _player_page()
    assert 'id="waitingOverlay"' in page
    assert 'class="row room-guest-controls"' in page
    assert 'body:not(.room-music) #videoStage>video' in page
    assert 'height:100%;max-height:none' in page
    assert 'stream.addTrack(event.track)' in page
    assert "video.addEventListener('playing'" in page
    assert 'video.videoWidth>0' in page
    assert 'id="retryMedia"' in page


def test_guest_chat_does_not_depend_on_host_only_peer_joined_event():
    page = _player_page()
    assert "if(host&&!guestPresent)" in page
    assert "if(!send('chat',msg))" in page
    assert "if(!guestPresent){note('الشخص التاني" not in page
