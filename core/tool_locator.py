"""Read-only discovery of installed Windows tools for BARQ.

Only fixed standard install locations are searched; the installer JSON inventory
is deliberately NOT used as a source of executable paths or permissions.
This lets a long-running BARQ process see new tools without trusting a mutable
manifest or requiring a Windows reboot to refresh its PATH.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


def _roots() -> tuple[Path, Path, Path]:
    return (Path(os.environ.get('ProgramFiles') or 'C:/Program Files'),
            Path(os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData/Local')),
            Path.home())


def find_tool(name: str) -> str | None:
    """Locate an approved executable in PATH or fixed vendor install folders."""
    base = Path(name).name.lower().removesuffix('.exe').removesuffix('.cmd')
    known = {
        'git', 'gh', 'node', 'npm', 'npx', 'code', 'python', 'py',
        'powershell', 'pwsh', 'winget', 'uv', 'windows-mcp',
        'ffmpeg', 'rg', 'fd', '7z', 'ollama', 'nvidia-smi',
    }
    if base not in known:
        return None
    cmd = shutil.which(name)
    if cmd:
        return str(Path(cmd).resolve())
    if sys.platform != 'win32':
        return None
    pf, local, home = _roots()
    candidates: dict[str, tuple[Path, ...]] = {
        'git': (pf/'Git/cmd/git.exe',),
        'gh': (pf/'GitHub CLI/gh.exe',),
        'node': (pf/'nodejs/node.exe',),
        'npm': (pf/'nodejs/npm.cmd',),
        'npx': (pf/'nodejs/npx.cmd',),
        'code': (local/'Programs/Microsoft VS Code/bin/code.cmd', pf/'Microsoft VS Code/bin/code.cmd'),
        'python': (local/'Programs/Python/Python311/python.exe',),
        'py': (Path(os.environ.get('WINDIR','C:/Windows'))/'py.exe',local/'Programs/Python/Launcher/py.exe'),
        'pwsh': (pf/'PowerShell/7/pwsh.exe',),
        'powershell': (Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe',),
        'uv': (home/'.local/bin/uv.exe',),
        'windows-mcp': (home/'.local/bin/windows-mcp.exe',),
        '7z': (pf/'7-Zip/7z.exe',),
        'nvidia-smi': (pf/'NVIDIA Corporation/NVSMI/nvidia-smi.exe',),
    }
    for candidate in candidates.get(base, ()):
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def hardware_monitor_folder() -> Path | None:
    """Pinned, SHA256-verified BARQ toolkit install location, if populated."""
    if sys.platform != 'win32':
        return None
    folder = _roots()[1] / 'BARQ/toolkit/hardware-monitor'
    if ((folder/'LibreHardwareMonitor.exe').is_file()
            and (folder/'LibreHardwareMonitorLib.dll').is_file()):
        return folder
    return None
