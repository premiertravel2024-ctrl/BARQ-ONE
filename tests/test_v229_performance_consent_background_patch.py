"""Fast offline regression checks for startup performance and explicit consent."""
import json
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def test_user_consent_only_changes_computer_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path))
    from desktop import apply_explicit_install_computer_consent
    state = tmp_path / 'computer_control_settings.json'
    state.write_text(json.dumps({'enabled': False, 'mode': 'ask-always',
        'allowed_folders': ['~/AgentWorkspace'], 'max_steps': 8}), encoding='utf-8')
    assert apply_explicit_install_computer_consent() == 0
    saved = json.loads(state.read_text(encoding='utf-8'))
    assert saved['enabled'] is True
    assert saved['mode'] == 'ask-always'
    assert saved['allowed_folders'] == ['~/AgentWorkspace']
    assert saved['max_steps'] == 8


def test_installer_never_grants_trusted_or_admin_rights(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path))
    from desktop import apply_explicit_install_computer_consent
    state = tmp_path / 'computer_control_settings.json'
    state.write_text(json.dumps({'enabled': False, 'mode': 'trusted'}))
    assert apply_explicit_install_computer_consent() == 0
    assert json.loads(state.read_text())['mode'] == 'smart'
    for name in ['installer.iss', 'installer_update.iss']:
        script = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
        assert 'Name: computerconsent' in script
        assert 'Flags: unchecked' in script
        assert '--setup-computer-consent' in script
        assert "ms-settings:privacy-microphone" in script
        assert 'PrivilegesRequired=lowest' in script


def test_background_and_startup_remain_opt_in():
    source = (ROOT / 'desktop.py').read_text(encoding='utf-8')
    assert '--setup-background-start' in source
    assert 'window.events.shown += start_wake_after_window_shown' in source
    assert 'threading.Thread(target=initialize_desktop_listener' in source
    assert 'initialize_desktop_listener()\n    from voice.wake' not in source
    for name in ('installer.iss','installer_update.iss'):
        text = (ROOT / 'scripts' / name).read_text(encoding='utf-8')
        assert 'Name: autostart;' in text
        assert '--setup-background-start' in text


def test_idle_status_poll_is_throttled():
    frontend = ROOT / 'frontend/src/components'
    computer = (frontend / 'workspace/ComputerControl.tsx').read_text(encoding='utf-8')
    voice = (frontend / 'layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    assert 'taskActive?1100:8000' in computer
    assert "if(!document.hidden)void poll()" in computer
    assert "7500" in voice
    assert "تشخيص الصوت المتقدم وتعليم النداء" in voice
    assert '<details' in voice


def test_wake_profile_disk_read_cached(tmp_path, monkeypatch):
    from voice.direct_wake import DirectWake, wake_fingerprint
    profile = tmp_path / 'wake_acoustic_profile.npz'
    profile.write_bytes(b'fixture')
    calls=[]
    monkeypatch.setattr(wake_fingerprint, 'load', lambda path: calls.append(path) or [object()] * wake_fingerprint.REPETITIONS)
    wake = DirectWake(lambda: None, lambda: False, lambda: None)
    monkeypatch.setattr(wake, '_templates_path', lambda: profile)
    assert wake.has_profile() and wake.has_profile()
    assert len(calls) == 1
    profile.unlink()
    assert not wake.has_profile()
