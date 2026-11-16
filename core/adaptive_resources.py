"""BARQ's portable, local resource governor.

No polling thread, hidden model downloads, background compute or elevated access.
Snapshots are on-demand and cached; only known measurements affect scheduling.
The GPU detector is informational: GPU inference is still owned by Ollama/provider.
"""
from __future__ import annotations

from core.processes import background_options
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from core.paths import state_file

MODES = ('eco', 'balanced', 'performance')
_MODE_DEFAULT = 'balanced'


def _memory_bytes() -> tuple[int | None, int | None]:
    """Total and available physical memory; None means unknown, not zero."""
    try:
        import psutil  # Optional: don't force a large install for resource hints.
        m = psutil.virtual_memory()
        return int(m.total), int(m.available)
    except (ImportError, AttributeError, OSError):
        pass
    if sys.platform == 'win32':
        try:
            from ctypes import wintypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [('dwLength', wintypes.DWORD), ('dwMemoryLoad', wintypes.DWORD),
                            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            data = MEMORYSTATUSEX()
            data.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(data)):
                return int(data.ullTotalPhys), int(data.ullAvailPhys)
        except (AttributeError, OSError, ValueError):
            pass
    if sys.platform.startswith('linux'):
        try:
            info = {}
            for line in Path('/proc/meminfo').read_text().splitlines():
                label, _, value = line.partition(':')
                if label in ('MemTotal', 'MemAvailable'):
                    info[label] = int(value.strip().split()[0]) * 1024
            return info.get('MemTotal'), info.get('MemAvailable')
        except (OSError, ValueError, IndexError):
            pass
    return None, None


# Native GetSystemTimes sampling avoids a mandatory psutil install on Windows.
# The first sample is deliberately non-blocking; subsequent snapshots estimate
# CPU utilization from the deltas, without a polling/background thread.
_WIN_CPU_PREV: tuple[int, int, int] | None = None
_WIN_CPU_LOCK = threading.Lock()


def _windows_cpu_percent() -> float | None:
    global _WIN_CPU_PREV
    try:
        class FILETIME(ctypes.Structure):
            _fields_ = [('dwLowDateTime', ctypes.c_ulong),
                        ('dwHighDateTime', ctypes.c_ulong)]
        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        def amount(value: FILETIME) -> int:
            return (value.dwHighDateTime << 32) | value.dwLowDateTime
        current = (amount(idle), amount(kernel), amount(user))
        with _WIN_CPU_LOCK:
            previous, _WIN_CPU_PREV = _WIN_CPU_PREV, current
        if previous is None:
            return None
        idle_delta = max(0, current[0] - previous[0])
        total_delta = max(0, (current[1] - previous[1]) + (current[2] - previous[2]))
        return round(min(100.0, max(0.0, 100.0 * (total_delta - idle_delta) / total_delta)), 1) if total_delta else None
    except (OSError, AttributeError, ValueError, ZeroDivisionError):
        return None


def _cpu_percent(cores: int) -> float | None:
    try:
        import psutil
        return min(100.0, max(0.0, float(psutil.cpu_percent(interval=None))))
    except (ImportError, AttributeError, ValueError):
        if sys.platform == 'win32':
            return _windows_cpu_percent()
        try:
            return round(min(100.0, max(0.0, os.getloadavg()[0] / max(1, cores) * 100)), 1)
        except (AttributeError, OSError):
            return None


def _gpu_devices() -> list[dict]:
    """Optional NVIDIA inventory; no local inference or persistent scanning."""
    path = shutil.which('nvidia-smi')
    if not path:
        return []
    try:
        result = subprocess.run([path, '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=1.5, check=False, **background_options())
        if result.returncode:
            return []
        devices = []
        for line in result.stdout.splitlines()[:8]:
            name, sep, memory = line.rpartition(',')
            if sep:
                try:
                    devices.append({'name': name.strip()[:100], 'vram_mb': int(memory.strip())})
                except ValueError:
                    continue
        return devices
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


class AdaptiveResources:
    def __init__(self, config_path: Path | None = None, sampler: Callable | None = None):
        self._config_path = config_path
        self._sampler = sampler
        self._lock = threading.RLock()
        self._last_sample: dict | None = None
        self._last_sample_at = 0.0
        self._gpu: list[dict] = []
        self._gpu_at = 0.0
        self._mode = _MODE_DEFAULT
        self._load_mode()

    @property
    def config_path(self) -> Path:
        return self._config_path if self._config_path is not None else state_file('adaptive-resources.json')

    def _load_mode(self) -> None:
        try:
            data = json.loads(self.config_path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and data.get('mode') in MODES:
                self._mode = data['mode']
        except (OSError, ValueError, TypeError):
            pass

    def mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError('Mode must be eco, balanced or performance')
        with self._lock:
            p = self.config_path
            p.parent.mkdir(parents=True, exist_ok=True)
            temp = p.with_name(p.name + '.tmp')
            try:
                temp.write_text(json.dumps({'mode': mode}), encoding='utf-8')
                os.replace(temp, p)
            finally:
                try: temp.unlink(missing_ok=True)
                except OSError: pass
            self._mode = mode

    def _sample(self) -> dict:
        cpu = max(1, os.cpu_count() or 1)
        total, available = _memory_bytes()
        return {'logical_cpu_cores': cpu, 'cpu_load_percent': _cpu_percent(cpu),
                'ram_total_bytes': total, 'ram_available_bytes': available}

    def snapshot(self, include_gpu: bool = False) -> dict:
        with self._lock:
            now = time.monotonic()
            if self._last_sample is None or now - self._last_sample_at > 3:
                measured = self._sampler() if self._sampler else self._sample()
                self._last_sample = dict(measured)
                self._last_sample_at = now
            data = dict(self._last_sample)
            if include_gpu and (self._gpu_at == 0 or now - self._gpu_at > 180):
                self._gpu = _gpu_devices()
                self._gpu_at = now
            data['gpus'] = list(self._gpu) if include_gpu else []
            data['gpu_checked'] = include_gpu
            data['platform'] = platform.system()
            data['mode'] = self._mode
            return data

    def policy(self) -> dict:
        # Fast on-demand snapshot: expensive GPU probes never run in the task path.
        data = self.snapshot()
        cores = max(1, int(data.get('logical_cpu_cores') or 1))
        load = data.get('cpu_load_percent')
        free = data.get('ram_available_bytes')
        mode = data['mode']
        workers = {'eco': 1, 'balanced': min(4, max(1, cores // 2)), 'performance': min(8, cores)}[mode]
        max_scan = {'eco': 120, 'balanced': 300, 'performance': 500}[mode]
        history = {'eco': 4, 'balanced': 8, 'performance': 12}[mode]
        if isinstance(load, (int, float)) and load >= 85:
            workers = 1
            max_scan = min(max_scan, 120)
            history = min(history, 6)
        if isinstance(free, (int, float)):
            if free < 512 * 1024**2:
                workers = 1
                max_scan = min(max_scan, 60)
                history = min(history, 4)
            elif free < 1536 * 1024**2:
                workers = min(workers, 2)
                max_scan = min(max_scan, 160)
        return {'mode': mode, 'scan_workers': workers, 'scan_max_files': max_scan,
                'routing_history_messages': history, 'context_chars_per_message': 1500 if mode == 'eco' else 2000,
                'note': 'Local adaptive limits. GPU acceleration is controlled by the selected model provider.'}

    def status(self) -> dict:
        return {'hardware': self.snapshot(include_gpu=True), 'limits': self.policy(),
                'modes': list(MODES), 'auto': True,'ollama_context_limit':self.ollama_context()}

    def ollama_context(self, model=None) -> int:
        """Budget native context using free RAM, profile and advertised model limit.

        This is a conservative memory hint, not a claim that every model fits.
        GPU inventory never implies GPU compute support or spare VRAM.
        """
        data=self.snapshot()
        available=data.get('ram_available_bytes')
        cap={'eco':4096,'balanced':8192,'performance':16384}[data['mode']]
        if isinstance(available,(int,float)):
            if available<1536*1024**2:cap=min(cap,2048)
            elif available<4*1024**3:cap=min(cap,4096)
            elif available<8*1024**3:cap=min(cap,8192)
        if (data.get('cpu_load_percent') or 0)>=85:cap=min(cap,4096)
        try:
            # An existing explicit setting is respected as an upper bound.
            cap=min(cap,max(2048,min(32768,int(os.getenv('OLLAMA_NUM_CTX') or cap))))
        except ValueError:pass
        if model is not None:
            cap=min(cap,max(512,int(model.context_window)))
        return cap


resources = AdaptiveResources()
