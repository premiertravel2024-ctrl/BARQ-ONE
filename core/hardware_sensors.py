"""Read-only, on-demand local hardware telemetry for BARQ voice and chat.

CPU temperatures are not exposed through a dependable generic Windows API.
LibreHardwareMonitor's local WMI provider supplies CPU sensors when running;
its official local .NET library is a read-only fallback when WMI is unavailable.
NVIDIA's signed driver provides GPU readings via nvidia-smi. No network,
no persistent logging, no shell text derived from user inputs, and no privilege
escalation. Values unavailable from sensors are never guessed.
"""
from __future__ import annotations

import json
import re
import urllib.request
import math
import os
import sys
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


# Fixed WMI query: never interpolate speech or user-supplied strings into commands.
_LHM_WMI_COMMAND = (
    "$ErrorActionPreference='Stop';"
    "Get-CimInstance -Namespace 'root\\LibreHardwareMonitor' -ClassName Sensor "
    "-Filter \"SensorType='Temperature'\" | "
    "Select-Object -First 120 Name,Identifier,Parent,Value,SensorType | "
    "ConvertTo-Json -Compress -Depth 3"
)
_NVIDIA_FIELDS = ['temperature.gpu', 'utilization.gpu', 'memory.used', 'memory.total']

# Installed by BARQ setup, not searched in arbitrary user/desktop folders. Never
# download a binary, request elevation, or run a model-provided command here.
_last_start_attempt = 0.0


def _monitor_executable() -> Path | None:
    roots = []
    if getattr(sys, 'frozen', False):
        roots.append(Path(sys.executable).resolve().parent)
    # Source/dev mode and the distribution's resource folder.
    from core.paths import resource
    roots.append(resource())
    local = os.environ.get('LOCALAPPDATA')
    if local:
        roots.extend((Path(local) / 'Programs' / 'AI Router Agent',
                      Path(local) / 'Programs' / 'BARQ',
                      Path(local) / 'BARQ'))
    # One-shot Windows toolkit setup stores a verified official release here.
    # This path is fixed by BARQ, not supplied by a model or an inventory file.
    from core.tool_locator import hardware_monitor_folder
    shared_monitor=hardware_monitor_folder()
    if shared_monitor is not None:
        roots.append(shared_monitor.parent)
    # The live source checkout can differ from the bundled PyInstaller resource.
    # Keep lookup restricted to BARQ's own trusted installation/source folders.
    roots.append(Path(__file__).resolve().parents[1])
    # Discover independently installed official LibreHardwareMonitor in
    # conventional vendor directories, not arbitrary user-supplied paths.
    if sys.platform == 'win32':
        for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            base = os.environ.get(key)
            if base:
                roots.extend((Path(base) / 'LibreHardwareMonitor',
                              Path(base) / 'Programs' / 'LibreHardwareMonitor'))

    seen: set[str] = set()
    for root in roots:
        folder = root if root.name.casefold() == 'librehardwaremonitor' else root / 'hardware-monitor'
        if str(folder).casefold() in seen:
            continue
        seen.add(str(folder).casefold())
        try:
            if not folder.is_dir():
                continue
            bundled = folder / 'bundled-v0.9.6' / 'LibreHardwareMonitor.exe'
            if bundled.is_file():
                return bundled
            direct = folder / 'LibreHardwareMonitor.exe'
            if direct.is_file():
                return direct
            # Installer release ZIPs can put the EXE one or two levels down.
            for child in sorted(folder.glob('*/LibreHardwareMonitor.exe')):
                if child.is_file():
                    return child
            for child in sorted(folder.glob('*/*/LibreHardwareMonitor.exe')):
                if child.is_file():
                    return child
        except (OSError, PermissionError):
            continue
    return _running_monitor_executable()


def _monitor_gui_running() -> bool:
    """Detect the official monitor by process name without requiring its path.

    The GUI may be elevated while BARQ is not. Windows then denies reading
    the process executable path even though its sensor window is visible.
    Avoid claiming the app is uninstalled or starting duplicate installers.
    """
    if sys.platform != 'win32':
        return False
    try:
        import psutil
    except ImportError:
        return False
    try:
        for process in psutil.process_iter(['name']):
            try:
                if str(process.info.get('name') or '').casefold() == 'librehardwaremonitor.exe':
                    return True
            except (OSError, PermissionError, psutil.Error):
                continue
    except (OSError, PermissionError, psutil.Error):
        return False
    return False


def _running_monitor_executable() -> Path | None:
    """Use only the OS-reported path of an already running LHM instance.

    This supports users who extract the portable official application to a
    custom directory. The exact named process and adjacent official DLL are
    required; we never recursively scan personal files or run an arbitrary
    model-provided path.
    """
    if sys.platform != 'win32':
        return None
    try:
        import psutil
    except ImportError:
        return None
    for process in psutil.process_iter(['name', 'exe']):
        try:
            if str(process.info.get('name') or '').casefold() != 'librehardwaremonitor.exe':
                continue
            raw = process.info.get('exe')
            if not raw:
                continue
            executable = Path(raw)
            if (executable.name.casefold() == 'librehardwaremonitor.exe'
                    and executable.is_file()
                    and (executable.parent / 'LibreHardwareMonitorLib.dll').is_file()):
                return executable
        except (OSError, PermissionError, psutil.Error):
            continue
    return None


def _start_installed_monitor(executable: Path) -> bool:
    global _last_start_attempt
    now = time.monotonic()
    if now - _last_start_attempt < 30:
        return False
    _last_start_attempt = now
    try:
        subprocess.Popen([str(executable)], cwd=str(executable.parent),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                         close_fds=True)
        return True
    except (OSError, ValueError, PermissionError):
        return False


# An explicit question about CPU sensors authorizes a narrowly-scoped attempt
# to install BARQ's optional official sensor provider. The installer cannot
# elevate, alter security settings or choose arbitrary download hosts.
_auto_setup_lock = threading.Lock()
_auto_setup_at: float | None = None
_auto_setup_process = None


def _sensor_install_script() -> Path | None:
    from core.paths import resource
    roots=[Path(sys.executable).resolve().parent] if getattr(sys,'frozen',False) else []
    roots.append(resource())
    for folder in roots:
        file=folder/'scripts'/'install_hardware_monitor.ps1'
        if file.is_file():return file
    return None


def auto_setup_sensors() -> str:
    """Start one official on-demand install; status, not proof of installation."""
    with _auto_setup_lock:
        return _start_sensor_setup()


def _start_sensor_setup() -> str:
    global _auto_setup_at,_auto_setup_process
    if not _is_windows() or os.environ.get('BARQ_DISABLE_SENSOR_AUTOSETUP')=='1':
        return 'disabled'
    if _monitor_executable():return 'installed'
    if _auto_setup_process is not None and _auto_setup_process.poll() is None:
        return 'running'
    if _auto_setup_at and time.monotonic()-_auto_setup_at<120:
        return 'retry_later'
    powershell=shutil.which('powershell.exe') or shutil.which('powershell')
    script=_sensor_install_script()
    if not powershell or script is None:return 'unavailable'
    _auto_setup_at=time.monotonic()
    try:
        from core.paths import state_file
        diagnostic=state_file('sensor-install.log')
        # The script is bundled with BARQ. No speech/model text is evaluated.
        with diagnostic.open('ab') as stream:
            _auto_setup_process=subprocess.Popen(
                [powershell,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                 '-File',str(script)],stdin=subprocess.DEVNULL,
                stdout=stream,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
        return 'started'
    except (OSError,ValueError,PermissionError):
        return 'unavailable'



def ensure_sensors_ready(timeout: float = 170) -> str:
    """Join the same fixed installer from simultaneous chat/voice requests."""
    status=auto_setup_sensors()
    if status not in ('started','running'):
        return status
    with _auto_setup_lock:
        process=_auto_setup_process
    if process is None:
        return 'unavailable'
    try:
        exit_code=process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return 'timeout'
    except OSError:
        return 'unavailable'
    return 'installed' if exit_code in (0,3) and _monitor_executable() else 'unavailable'

def _query_lhm(executable: str, *, timeout: float = 2) -> str | None:
    return _run([executable, '-NoProfile', '-NonInteractive', '-Command', _LHM_WMI_COMMAND],
                timeout=timeout)


def _query_local_library(powershell: str, monitor_exe: Path, *, timeout: float = 6) -> str | None:
    """Fallback: query the trusted, bundled LHM .NET DLL without WMI or internet.

    Only a fixed BARQ-owned script and the local installed monitor path are
    passed to PowerShell. No generated/model-supplied commands are accepted.
    """
    root = monitor_exe.parent
    libraries = (root / 'LibreHardwareMonitorLib.dll',
                 root / 'LibreHardwareMonitor' / 'LibreHardwareMonitorLib.dll')
    library = next((p for p in libraries if p.is_file()), None)
    from core.paths import resource
    scripts=[monitor_exe.parent.parent / 'scripts' / 'read_hardware_monitor.ps1',
             Path(sys.executable).resolve().parent / 'scripts' / 'read_hardware_monitor.ps1',
             Path(__file__).resolve().parents[1] / 'scripts' / 'read_hardware_monitor.ps1',
             resource('scripts','read_hardware_monitor.ps1')]
    script=next((candidate for candidate in scripts if candidate.is_file()),None)
    if library is None or script is None:
        return None
    return _run([powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                 '-File', str(script), '-LibraryPath', str(library)], timeout=timeout)



def _run(command: list[str], timeout: float) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                                timeout=timeout, check=False,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout[:32768]


def _valid_temperature(value: Any) -> float | None:
    try:
        temp = float(value)
    except (TypeError, ValueError):
        return None
    return round(temp, 1) if math.isfinite(temp) and 0 < temp < 125 else None


def _sensor_kind(sensor: dict) -> str | None:
    name = str(sensor.get('Name') or '').lower()
    path = ' '.join(str(sensor.get(p) or '') for p in ('Identifier','Parent')).lower()
    # Do not treat the motherboard's CPU-adjacent thermal zone as CPU package
    # when the label doesn't say CPU; prioritise identified processor sensors.
    # Hardware identifiers are more reliable than names. GPU Package must
    # NEVER be mistaken for CPU Package; motherboard "CPU socket" temperature
    # is not the on-die CPU sensor requested by the user.
    if any(x in path for x in ('/intelcpu/', '/amdcpu/', '/cpu/', '\\cpu\\')):
        return 'cpu'
    if any(x in path for x in ('/nvidiagpu/', '/atigpu/', '/intelgpu/', '/gpu/',
                                '/gpu-nvidia/', '/gpu-amd/', '/gpu-intel/')):
        return 'gpu'
    if any(x in path for x in ('/hdd/', '/storage/')):
        return 'storage'
    if any(x in path for x in ('/lpc/', '/motherboard/', '/mainboard/', '/superio/')):
        return None
    if 'gpu' in name or 'hot spot' in name:
        return 'gpu'
    if ('cpu' in name or 'tctl/tdie' in name or 'ccd' in name):
        return 'cpu'
    if 'ssd' in name or 'nvme' in name:
        return 'storage'
    return None


def _preferred_cpu_sensor(sensors: list[dict]) -> dict | None:
    def rank(s: dict) -> tuple[int, str]:
        label = str(s.get('name') or '').lower()
        path = str(s.get('Identifier') or '').lower()
        if 'package' in label or 'tctl/tdie' in label: return (0, label)
        if 'core average' in label or 'cpu core' in label: return (1, label)
        if '/intelcpu/' in path or '/amdcpu/' in path: return (2, label)
        return (3, label)
    return sorted(sensors,key=rank)[0] if sensors else None


def _is_windows() -> bool:
    return sys.platform == 'win32'

def _decode_temperature_records(output: str | None) -> list[dict]:
    """Parse only measured, labelled temperature values, never a guessed zone."""
    if not output:
        return []
    try:
        values = json.loads(output)
    except (TypeError, ValueError):
        return []
    records = values if isinstance(values, list) else [values]
    return [record for record in records[:120] if isinstance(record, dict)
            and str(record.get('SensorType') or 'Temperature').lower() == 'temperature'
            and _valid_temperature(record.get('Value')) is not None]


def _collect_temperatures(records: list[dict]) -> dict:
    candidates: dict[str, list[dict]] = {'cpu': [], 'gpu': [], 'storage': []}
    for sensor in records:
        kind = _sensor_kind(sensor)
        temp = _valid_temperature(sensor.get('Value'))
        if temp is not None and kind in candidates:
            candidates[kind].append({'name': str(sensor.get('Name') or '')[:75],
                                     'temp': temp,
                                     'Identifier': str(sensor.get('Identifier') or '')})
    result: dict[str, Any] = {'cpu_c': None, 'gpu_c': None, 'storage_c': None,
                              'cpu_sensor': None}
    cpu = _preferred_cpu_sensor(candidates['cpu'])
    if cpu:
        result['cpu_c'] = cpu['temp']
        result['cpu_sensor'] = cpu['name']
    for kind in ('gpu', 'storage'):
        if candidates[kind]:
            result[kind + '_c'] = candidates[kind][0]['temp']
    return result



# Read LHM's own live sensor feed before starting PowerShell or a second
# privileged hardware reader. 127.0.0.1 and a fixed path/port are intentional:
# no untrusted URLs, proxies, LAN probing or remote sensor commands.
_LHM_HTTP_URL = 'http://127.0.0.1:8085/data.json'
_http_lock = threading.Lock()
_http_reading: dict | None = None
_http_reading_at = 0.0


def _http_temperature(value: Any) -> float | None:
    """LHM HTTP RawValue is numeric in some versions, '64.0 °C' in others."""
    if isinstance(value, (float, int)):
        return _valid_temperature(value)
    if not isinstance(value, str):
        return None
    matched = re.fullmatch(r'\s*([+-]?\d+(?:[.,]\d+)?)\s*(?:°\s*C|C)?\s*',
                           value, flags=re.I)
    if not matched:
        return None
    return _valid_temperature(matched.group(1).replace(',', '.'))


def _parse_http_sensor_tree(tree: object) -> list[dict]:
    """Extract only temperature sensors from LHM's authenticated JSON shape."""
    if not isinstance(tree, dict) or not isinstance(tree.get('Children'), list) or not tree.get('Version'):
        return []
    records: list[dict] = []
    visited = 0

    def walk(node: object, hardware_id: str = '', depth: int = 0) -> None:
        nonlocal visited
        if not isinstance(node, dict) or depth > 12 or visited > 2048:
            return
        visited += 1
        parent = str(node.get('HardwareId') or hardware_id)[:160]
        if str(node.get('Type') or '').casefold() == 'temperature':
            identifier = str(node.get('SensorId') or '')[:180]
            value = _http_temperature(node.get('RawValue'))
            if value is None:
                value = _http_temperature(node.get('Value'))
            if identifier and value is not None:
                records.append({
                    'Name': str(node.get('Text') or '')[:100],
                    'Identifier': identifier,
                    'Parent': parent,
                    'SensorType': 'Temperature',
                    'Value': value,
                })
        children = node.get('Children')
        if isinstance(children, list):
            for child in children[:128]:
                walk(child, parent, depth + 1)
    walk(tree)
    return records


def _read_local_http() -> dict | None:
    """Fast read-only localhost snapshot when LHM Remote Web Server is enabled.

    Caches only a successful recent sample to keep repeated chat/monitor polls
    from spawning PowerShell. A failed request never fabricates sensor values.
    """
    global _http_reading, _http_reading_at
    with _http_lock:
        if _http_reading and time.monotonic() - _http_reading_at < 1.5:
            return dict(_http_reading)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(_LHM_HTTP_URL, headers={'Accept': 'application/json'})
        with opener.open(request, timeout=0.45) as response:
            if response.status != 200:
                return None
            payload = response.read(524289)
            if len(payload) > 524288:
                return None
        records = _parse_http_sensor_tree(json.loads(payload))
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
    measured = _collect_temperatures(records)
    if measured['cpu_c'] is None and measured['gpu_c'] is None and measured['storage_c'] is None:
        return None
    measured['provider'] = 'LibreHardwareMonitor (local HTTP)'
    measured['measured_at'] = time.time()
    with _http_lock:
        _http_reading = dict(measured)
        _http_reading_at = time.monotonic()
    return measured


def read_local_temperatures() -> dict:
    """Read real sensor values. If WMI omits CPU, retry the direct .NET DLL."""
    result: dict[str, Any] = {'provider': None, 'cpu_c': None, 'gpu_c': None,
                              'storage_c': None, 'cpu_sensor': None}
    if not _is_windows():
        result['reason'] = 'windows_only'
        return result
    # The live LHM HTTP feed works even when PowerShell / WMI is blocked.
    # Attempt it FIRST, before looking up or spawning any other process.
    live_http = _read_local_http()
    if live_http and live_http.get('cpu_c') is not None:
        return {**result, **live_http}

    powershell = shutil.which('powershell.exe') or shutil.which('powershell')
    if not powershell:
        result['reason'] = 'powershell_unavailable'
        return result

    wmi_output = _query_lhm(powershell)
    wmi_broken = bool(wmi_output and not _decode_temperature_records(wmi_output))
    wmi = _collect_temperatures(_decode_temperature_records(wmi_output))
    result.update(wmi)
    if wmi['cpu_c'] is not None:
        result['provider'] = 'LibreHardwareMonitor (local WMI)'
        return result

    monitor = _monitor_executable()
    local_failure = None
    if monitor is not None:
        if not any(candidate.is_file() for candidate in (
                monitor.parent / 'LibreHardwareMonitorLib.dll',
                monitor.parent / 'LibreHardwareMonitor' / 'LibreHardwareMonitorLib.dll')):
            local_failure = 'sensor_library_missing'
        # Some LHM versions expose GPU sensors through WMI but not CPU.
        # Still try the bundled, signed-off-by-user local DLL in that case.
        direct_output = _query_local_library(powershell, monitor)
        if direct_output is None and local_failure is None:
            local_failure = 'sensor_library_unavailable'
        direct = _collect_temperatures(_decode_temperature_records(direct_output))
        for field in ('cpu_c', 'gpu_c', 'storage_c', 'cpu_sensor'):
            if result[field] is None and direct[field] is not None:
                result[field] = direct[field]
        if direct['cpu_c'] is not None:
            result['provider'] = 'LibreHardwareMonitor (local .NET)'
            return result
        # If the app exposes only WMI sensors after launching, retry briefly.
        if not any(result[key] is not None for key in ('cpu_c', 'gpu_c', 'storage_c')):
            # Never launch a second instance when the user already opened the
            # standalone portable monitor (possibly as Administrator).
            already_running = _running_monitor_executable()
            if already_running is None or already_running != monitor:
                launched = _start_installed_monitor(monitor)
            else:
                launched = False
            if launched:
                result['launched_local_provider'] = True
                for _ in range(3):
                    time.sleep(0.45)
                    retry = _collect_temperatures(_decode_temperature_records(
                        _query_lhm(powershell, timeout=2)))
                    if retry['cpu_c'] is not None:
                        result.update(retry)
                        result['provider'] = 'LibreHardwareMonitor (local WMI)'
                        return result
                    for field in ('gpu_c', 'storage_c'):
                        if result[field] is None:
                            result[field] = retry[field]
        result['installed_path'] = str(monitor.parent)
    # A live HTTP server can provide GPU/storage even if no CPU sensor was
    # exported; never re-label that reading as CPU temperature.
    if live_http:
        for field in ('gpu_c', 'storage_c'):
            if result.get(field) is None and live_http.get(field) is not None:
                result[field] = live_http[field]
    if any(result[k] is not None for k in ('cpu_c', 'gpu_c', 'storage_c')):
        result['provider'] = 'LibreHardwareMonitor (local WMI/.NET)'
        if result['cpu_c'] is None:
            result['reason'] = 'no_matching_sensors'
    elif monitor is None:
        # Seeing the elevated GUI does not imply its WMI namespace is present.
        # Do not attempt another install when the user already has it running.
        running = _monitor_gui_running()
        result['reason'] = 'sensor_provider_unavailable' if running or wmi_broken else 'monitor_not_installed'
    else:
        result['reason'] = local_failure or 'sensor_provider_unavailable'
    return result


def read_nvidia_gpu() -> dict:
    """Get GPU temperature/utilization from the installed NVIDIA driver."""
    exe=shutil.which('nvidia-smi')
    if not exe:
        return {}
    output=_run([exe,'--query-gpu='+','.join(_NVIDIA_FIELDS),
                 '--format=csv,noheader,nounits'],timeout=3)
    if not output:
        return {}
    line=output.strip().splitlines()[0] if output.strip() else ''
    values=[v.strip() for v in line.split(',')]
    if len(values)!=4:return {}
    temp=_valid_temperature(values[0])
    def safe_float(value: str) -> float | None:
        try:
            number=float(value)
            return number if math.isfinite(number) and number>=0 else None
        except (TypeError,ValueError):
            return None
    usage=safe_float(values[1]); used=safe_float(values[2]); total=safe_float(values[3])
    result={'source':'NVIDIA driver'}
    if temp is not None:result['gpu_c']=temp
    if usage is not None and usage<=100:result['gpu_load_percent']=round(usage)
    if used is not None and total is not None and total>0 and used<=total:
        result['vram_used_mb']=round(used)
        result['vram_total_mb']=round(total)
    return result if len(result)>1 else {}


def snapshot(include_gpu: bool = True) -> dict:
    """On-demand sensor summary: never invent a CPU reading from an ACPI zone."""
    temperatures=read_local_temperatures()
    nvidia=read_nvidia_gpu() if include_gpu else {}
    if temperatures.get('gpu_c') is None and nvidia.get('gpu_c') is not None:
        temperatures['gpu_c']=nvidia['gpu_c']
        temperatures['gpu_source']='NVIDIA driver'
    temperatures.update({k:v for k,v in nvidia.items() if k not in ('source','gpu_c')})
    return temperatures
