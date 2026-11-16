"""Static and offline regression checks for packaged wake and computer-control opt-in."""
from pathlib import Path
from computer_control.safety.policy import Policy
from computer_control.executor.manager import Manager
from computer_control.adapters.base import FakeAdapter
from computer_control.api import load_policy
import pytest

ROOT=Path(__file__).resolve().parents[1]

def test_disabled_by_default_in_real_desktop_policy(monkeypatch,tmp_path):
    from computer_control import api
    monkeypatch.setattr(api,'state_file',lambda _:tmp_path/'computer_control_settings.json')
    monkeypatch.setattr(api,'resource',lambda *parts:ROOT.joinpath(*parts))
    assert api.load_policy().enabled is False

def test_control_toggle_blocks_real_actions():
    m=Manager(FakeAdapter(),policy=Policy(enabled=False))
    with pytest.raises(RuntimeError,match='disabled'):
        m.start('open calculator',start_task=False)
    with pytest.raises(RuntimeError,match='disabled'):
        m.launch_direct('open_app',{'name':'notepad'},'voice')
    assert m.settings()['enabled'] is False
    m.set_policy(enabled=True)
    assert m.settings()['enabled'] is True
    m.set_policy(enabled=False)
    assert m.settings()['enabled'] is False

def test_installer_includes_wake_runtime_and_explicit_model_consent():
    installer=(ROOT/'scripts/installer.iss').read_text(encoding='utf-8')
    builder=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    vbs=(ROOT/'START_BARQ_WAKE_AR.vbs').read_text(encoding='utf-8')
    assert 'Name: arabicwake' in installer
    assert 'CreateDownloadPage' in installer
    assert 'WakeDownloadPage.Download' in installer
    assert '--install-model-from-archive' in installer
    assert 'SW_HIDE' in installer and 'ewWaitUntilTerminated' in installer
    assert "WizardIsTaskSelected('arabicwake')" in installer
    assert '--collect-all' in builder and "'BARQ_Wake'" in builder
    assert 'dist\\BARQ\\BARQ_Wake.exe' in builder
    assert 'BARQ_Wake.exe' in vbs and 'FileExists' in vbs
    assert '--self-test' in (ROOT/'scripts/barq_wake_vosk.py').read_text(encoding='utf-8')
    assert 'BARQ_Wake.exe' in (ROOT/'scripts/smoke_install.ps1').read_text(encoding='utf-8')

def test_tooltip_handles_focus_and_window_changes():
    tooltip=(ROOT/'frontend/src/components/ui/Tooltip.tsx').read_text(encoding='utf-8')
    for word in ('pointermove','pointerdown','scroll','resize','blur',':focus-visible','onPointerLeave'):
        assert word in tooltip
