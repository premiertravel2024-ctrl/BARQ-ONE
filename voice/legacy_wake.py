"""Safely retire only obsolete BARQ wake listeners from this exact installation.

Opt-in happens when BARQ's own wake setting is enabled. Never terminate another
application, a different BARQ installation, or an unrelated Python process.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def installation_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _same_path(one: str | Path, other: Path) -> bool:
    try:
        return str(Path(one).resolve()).casefold() == str(other.resolve()).casefold()
    except (OSError, ValueError, TypeError):
        return False


def is_own_legacy_wake(process_info: dict, root: Path) -> bool:
    """Require an EXACT known installed path, never process-name-only matching."""
    executable = process_info.get('exe') or ''
    cmdline = process_info.get('cmdline') or []
    if _same_path(executable, root / 'BARQ_Wake.exe'):
        return True
    # Old source-mode helpers sometimes ran with pythonw.exe, but we may only
    # stop them when the exact script argument points inside THIS BARQ source.
    executable_name = Path(str(executable)).name.casefold()
    if executable_name not in ('python.exe', 'pythonw.exe', 'python'):
        return False
    # Never match a script path merely mentioned as data by another program.
    script_arg = next((arg for arg in cmdline[1:] if isinstance(arg, str)
                       and not arg.startswith('-')), None)
    return bool(script_arg and _same_path(script_arg, root / 'scripts' / 'barq_wake_vosk.py'))


def retire_legacy_listeners(root: Path | None = None, process_lib=None) -> tuple[bool, str]:
    """Remove conflicting legacy companion from the same install on opt-in.

    Never kill arbitrarily; graceful terminate only. A refusal or timeout is
    surfaced so the UI can instruct the user to close the old tray explicitly.
    """
    if sys.platform != 'win32' and process_lib is None:
        return True, ''
    if process_lib is None:
        try:
            import psutil as process_lib
        except ImportError:
            return False, 'psutil not available; update BARQ desktop dependencies'
    root = (root or installation_root()).resolve()
    try:
        others = list(process_lib.process_iter(['pid', 'exe', 'cmdline']))
    except (OSError, RuntimeError) as exc:
        return False, f'Unable to enumerate BARQ wake helpers: {type(exc).__name__}'
    for proc in others:
        try:
            if proc.pid == os.getpid() or not is_own_legacy_wake(proc.info, root):
                continue
            proc.terminate()
            proc.wait(timeout=3)
        except process_lib.NoSuchProcess:
            continue
        except (process_lib.AccessDenied, process_lib.TimeoutExpired, OSError):
            return False, 'اقفل مساعد التنبيه القديم من الأيقونة جنب الساعة، وبعدها اضغط إعادة تشغيل الاستماع.'
    return True, ''
