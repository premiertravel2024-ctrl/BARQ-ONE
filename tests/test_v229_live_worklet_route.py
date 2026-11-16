"""Regression for BARQ v2.29 desktop voice 404, separate from Gemini networking."""
from pathlib import Path
from fastapi.testclient import TestClient
import api

ROOT = Path(__file__).resolve().parents[1]


def test_worklet_is_served_by_real_barq_api_and_is_executable_js():
    with TestClient(api.app) as client:
        response = client.get('/audio/live-capture.js')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/javascript')
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert b"registerProcessor('barq-capture'" in response.content
    assert response.content == (ROOT/'web/react/audio/live-capture.js').read_bytes()


def test_missing_worklet_fails_with_clear_404_not_an_html_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'react_dist', tmp_path)
    with TestClient(api.app) as client:
        response = client.get('/audio/live-capture.js')
    assert response.status_code == 404
    assert 'application/json' in response.headers['content-type']
    assert 'missing' in response.json()['detail'].lower()


def test_source_and_bundled_worklet_are_identical():
    assert (ROOT/'frontend/public/audio/live-capture.js').read_bytes() == (ROOT/'web/react/audio/live-capture.js').read_bytes()


def test_release_guard_keeps_live_voice_asset_in_exe():
    script = (ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert "web/react/audio/live-capture.js" in script
    assert "frontend/public/audio/live-capture.js" in script
    assert "'--add-data', 'web;web'" in script
    health = (ROOT/'desktop.py').read_text(encoding='utf-8')
    assert "client.get('/audio/live-capture.js')" in health
    assert "127.0.0.1:{port}/audio/live-capture.js" in health
