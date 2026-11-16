"""One interactive BARQ instance per Windows profile.

Launching BARQ while its window is hidden reopens the existing installation,
not a second voice listener competing for the microphone.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import urllib.request

from core.paths import data_dir

_mutex = None


def _mutex_key():
    digest = hashlib.sha256(str(data_dir()).lower().encode('utf-8')).hexdigest()[:24]
    return 'Local\\BARQ-AI-' + digest


def already_running() -> bool:
    global _mutex
    if sys.platform != 'win32':
        return False
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, _mutex_key())
    if not mutex:
        raise OSError('Could not create BARQ Windows instance mutex')
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(mutex)
        return True
    _mutex = (kernel, mutex)
    return False


def show_existing() -> bool:
    from voice.wake import discovery_file
    try:
        record = json.loads(discovery_file().read_text(encoding='utf-8'))
        port = int(record['port'])
        token = str(record['token'])
        if not (1 <= port <= 65535) or not token:
            return False
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}/v1/voice/wake/show', data=b'{}',
            headers={'X-BARQ-Wake-Token': token, 'Content-Type': 'application/json'},
            method='POST')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3) as response:
            return response.status == 200
    except (OSError, ValueError, KeyError, TypeError, TimeoutError):
        return False


def release() -> None:
    global _mutex
    if _mutex is not None:
        kernel, handle = _mutex
        kernel.CloseHandle(handle)
        _mutex = None
