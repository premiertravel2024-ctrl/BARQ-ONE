"""Explicit per-user startup setting for the installed Windows BARQ.exe."""
from pathlib import Path
import sys

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
ENTRY = 'BARQ AI'


def supported() -> bool:
    return sys.platform == 'win32' and bool(getattr(sys, 'frozen', False))


def _command() -> str:
    return f'"{Path(sys.executable).resolve()}" --background'


def is_enabled() -> bool:
    if not supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            actual, _ = winreg.QueryValueEx(key, ENTRY)
        return actual.casefold() == _command().casefold()
    except (OSError, ImportError):
        return False


def configure(enabled: bool) -> None:
    if not supported():
        raise RuntimeError('Startup option is available in the installed Windows BARQ app only')
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, ENTRY, 0, winreg.REG_SZ, _command())
        else:
            try:
                actual, _ = winreg.QueryValueEx(key, ENTRY)
                if actual.casefold() == _command().casefold():
                    winreg.DeleteValue(key, ENTRY)
            except FileNotFoundError:
                pass
