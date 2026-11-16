"""LibreHardwareMonitor remains read-only, pinned, and available in chat/voice."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from core import hardware_sensors as hw
from core import windows_facts
from voice import computer_tools

ROOT = Path(__file__).resolve().parents[1]


def test_gpu_only_wmi_does_not_mask_real_cpu_from_direct_library(monkeypatch, tmp_path):
    monitor = tmp_path / 'hardware-monitor' / 'LibreHardwareMonitor.exe'
    monitor.parent.mkdir(); monitor.touch()
    monkeypatch.setattr(hw, '_is_windows', lambda: True)
    monkeypatch.setattr(hw.shutil, 'which', lambda _: 'powershell.exe')
    monkeypatch.setattr(hw, '_monitor_executable', lambda: monitor)
    monkeypatch.setattr(hw, '_query_lhm', lambda *a, **kw: '[{"Name":"GPU Core","Identifier":"/nvidiagpu/0/temperature/0","Value":54}]')
    monkeypatch.setattr(hw, '_query_local_library', lambda *a, **kw: '[{"Name":"CPU Package","Identifier":"/intelcpu/0/temperature/0","Value":70}]')
    reading = hw.read_local_temperatures()
    assert reading['cpu_c'] == 70 and reading['gpu_c'] == 54
    assert reading['provider'] == 'LibreHardwareMonitor (local .NET)'


def test_invalid_sensor_values_are_never_fabricated(monkeypatch, tmp_path):
    monitor = tmp_path / 'hardware-monitor' / 'LibreHardwareMonitor.exe'
    monitor.parent.mkdir(); monitor.touch()
    monkeypatch.setattr(hw, '_is_windows', lambda: True)
    monkeypatch.setattr(hw.shutil, 'which', lambda _: 'powershell.exe')
    monkeypatch.setattr(hw, '_monitor_executable', lambda: monitor)
    monkeypatch.setattr(hw, '_query_lhm', lambda *a, **kw: '[{"Name":"CPU Package","Identifier":"/intelcpu/0/temperature/0","Value":0}]')
    monkeypatch.setattr(hw, '_query_local_library', lambda *a, **kw: None)
    monkeypatch.setattr(hw, '_start_installed_monitor', lambda *a: False)
    reading = hw.read_local_temperatures()
    assert reading['cpu_c'] is None and reading['reason'] == 'sensor_provider_unavailable'


@pytest.mark.asyncio
async def test_voice_temperature_read_does_not_need_full_desktop_consent(monkeypatch):
    import voice.computer_tools as t
    monkeypatch.setattr(t.sys, 'platform', 'win32')
    monkeypatch.setattr(windows_facts.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(windows_facts, '_answer_sensor_question', lambda _: 'حرارة المعالج 65 درجة مئوية')
    monkeypatch.setattr(windows_facts, 'snapshot', lambda: {})
    manager = SimpleNamespace(policy=SimpleNamespace(enabled=False))
    result = await computer_tools.dispatch_computer_tool('get_pc_system_facts', {'question': 'درجة حرارة المعالج كام؟'}, manager_instance=manager)
    assert result['status'] == 'ok' and '65' in result['message']
    blocked = await computer_tools.dispatch_computer_tool('get_pc_system_facts', {'question': 'سعة الرام كام؟'}, manager_instance=manager)
    assert blocked['status'] == 'disabled'


def test_installer_pins_verified_official_release_and_includes_sensor_tasks():
    src = (ROOT / 'scripts/install_hardware_monitor.ps1').read_text()
    assert '/releases/download/v0.9.6/LibreHardwareMonitor.zip' in src
    assert '086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001' in src
    assert '$Hasher.ComputeHash($ZipStream)' in src and 'SHA256 mismatch' in src
    assert 'LibreHardwareMonitorLib.dll' in src
    assert (ROOT / 'STAGE_BARQ_SENSORS.bat').is_file()
    for name in ('installer.iss','installer_update.iss'):
        body = (ROOT / 'scripts' / name).read_text()
        assert 'Name: hardwaresensors;' in body
        if name=='installer.iss':
            # Setup recursively copies the same binary directory as portable.
            assert 'Source: "{#BinaryDir}\\*"' in body
            assert 'Copy-Item -LiteralPath $monitorRoot' in (ROOT/'scripts/build_windows.ps1').read_text()
        else:
            assert 'Source: "..\\hardware-monitor\\*"' in body
        assert 'CHECK_BARQ_SENSORS.bat' in body
