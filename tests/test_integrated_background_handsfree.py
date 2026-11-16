"""Regression suite for close-to-tray and natural-conversation wake routing."""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def test_window_close_hides_and_does_not_destroy_app(monkeypatch):
    from voice.background_window import BackgroundWindow
    w = Mock()
    ctl = BackgroundWindow(w, ROOT / 'assets/barq-tray-32.png')
    timers=[]
    class FakeTimer:
        def __init__(self, *args): timers.append(self)
        def start(self): pass
        def cancel(self): pass
    def fake_thread(**kwargs):
        return Mock(start=lambda: kwargs['target'](*kwargs.get('args', ())))
    monkeypatch.setattr('voice.background_window.threading.Timer', FakeTimer)
    monkeypatch.setattr('voice.background_window.threading.Thread', fake_thread)
    assert ctl.on_closing() is False
    w.hide.assert_called_once()
    w.evaluate_js.assert_not_called()
    w.destroy.assert_not_called()
    ctl.quit_requested = True
    assert ctl.on_closing() is True


def test_wake_window_show_without_external_tool_access(monkeypatch):
    import voice.background_window as bg
    w = Mock()
    ctl = bg.BackgroundWindow(w, ROOT / 'assets/barq-tray-32.png')
    monkeypatch.setattr(bg, '_active', ctl)
    import voice.wake as wake
    monkeypatch.setattr(wake,'wake_preferences',lambda:{'show_on_wake':True})
    bg.show_on_wake()
    w.show.assert_called_once()
    w.restore.assert_called_once()


def test_pausing_tray_listener_persists_disabled_state(monkeypatch):
    from voice.background_window import BackgroundWindow
    import voice.wake as wake
    ctl = BackgroundWindow(Mock(), ROOT / 'assets/barq-tray-32.png')
    stop = Mock()
    enable = Mock()
    monkeypatch.setattr(wake, 'stop_listener', stop)
    monkeypatch.setattr(wake, 'set_wake_enabled_from_tray', enable)
    ctl.pause()
    stop.assert_called_once()
    enable.assert_called_once_with(False)


def test_background_only_routes_wake_to_handsfree_and_keeps_computer_opt_in():
    app = (ROOT / 'frontend/src/App.tsx').read_text(encoding='utf-8')
    settings = (ROOT / 'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    assert 'barq-handsfree-start' in app
    assert 'wake_computer_enabled' in settings
    assert 'LiveVoiceDialog autoStart' not in app
    assert "self.window.hide()" in (ROOT / 'voice/background_window.py').read_text(encoding='utf-8')


def test_reject_untrusted_instance_reopen_request():
    import api
    with TestClient(api.app) as client:
        result = client.post('/v1/voice/wake/show', headers={'X-BARQ-Wake-Token': 'invalid'})
        assert result.status_code == 403


def test_wake_pending_computer_defaults_off(monkeypatch,tmp_path):
    import voice.wake as wake
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    status=wake.wake_preferences()
    assert status['enabled'] is False
    assert status['wake_computer_enabled'] is False
    pending=wake.wake_pending()
    assert pending['computer_enabled'] is False


def test_desktop_packages_its_own_tray():
    build = (ROOT / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert "'--collect-all', 'pystray'" in build
    assert "'--add-data', 'assets;assets'" in build
    desktop = (ROOT / 'desktop.py').read_text(encoding='utf-8')
    assert "start_hidden='--background' in sys.argv" in desktop
    assert 'already_running()' in desktop
