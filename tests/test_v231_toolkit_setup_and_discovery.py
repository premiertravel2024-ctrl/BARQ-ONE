"""Regression tests for installed tools missing from BARQ's stale process PATH."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from core import tool_locator


def test_tool_locator_refuses_arbitrary_programs():
    assert tool_locator.find_tool('random-model-command') is None
    assert tool_locator.find_tool('../malicious.exe') is None


def test_find_tool_prefers_process_path_without_installer_inventory(tmp_path):
    # Cross-platform path: /usr/local/bin/git becomes C:\usr\local\bin\git
    # on Windows, even though the locator correctly resolves the PATH entry.
    installed = tmp_path / 'git.exe'
    installed.write_bytes(b'test executable placeholder')
    with patch.object(tool_locator.shutil, 'which', return_value=str(installed)):
        assert tool_locator.find_tool('git') == str(installed.resolve())


def test_fixed_lhm_toolkit_install_is_detected(tmp_path):
    folder = tmp_path / 'BARQ' / 'toolkit' / 'hardware-monitor'
    folder.mkdir(parents=True)
    (folder / 'LibreHardwareMonitor.exe').write_bytes(b'unit-test')
    assert tool_locator.hardware_monitor_folder() is None or tool_locator.hardware_monitor_folder() != folder
    (folder / 'LibreHardwareMonitorLib.dll').write_bytes(b'unit-test')
    with patch.object(tool_locator.sys, 'platform', 'win32'), patch.object(tool_locator, '_roots', return_value=(tmp_path,tmp_path,tmp_path)):
        assert tool_locator.hardware_monitor_folder() == folder
        from core import hardware_sensors
        assert hardware_sensors._monitor_executable() == folder / 'LibreHardwareMonitor.exe'


def test_installer_has_fixed_official_sources_no_unreviewed_privilege_escalation():
    src = (Path(__file__).resolve().parents[1] / 'INSTALL_BARQ_TOOLKIT.ps1').read_text(encoding='utf-8')
    for token in ('Git.Git', 'OpenJS.NodeJS.LTS', 'GitHub.cli', 'Microsoft.VisualStudioCode',
                  'Microsoft.PowerShell', 'BurntSushi.ripgrep.MSVC', 'sharkdp.fd',
                  'LibreHardwareMonitor.zip', 'windows-mcp==0.8.8', 'Get-FileHash',
                  'installed-tools.json', '-PlanOnly'):
        assert token.lstrip('-') in src or token in src
    assert 'Start-Process -Verb RunAs' not in src
    assert 'Set-ExecutionPolicy Unrestricted' not in src
    assert 'Invoke-Expression' not in src
    assert 'http://0.0.0.0' not in src


def test_runner_uses_locator_only_when_tool_not_on_path():
    from execution.runner import Runner
    with patch('execution.runner.os.name', 'nt'), patch('execution.runner.shutil.which', return_value=None), \
         patch('core.tool_locator.find_tool', return_value=None) as locator:
        try:
            Runner.resolve('git')
        except Exception:
            pass
        locator.assert_called_once_with('git')
