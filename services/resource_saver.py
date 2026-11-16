"""Safe, reversible, explicit-consent Windows resource saver for BARQ.

Process suspension is restricted to reviewed non-essential names. BARQ never
terminates processes, changes service startup configuration, or elevates.
A timer, normal-exit handler, and startup recovery resume paused tasks.
No process is automatically paused merely by selecting a mode.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import sys
from pathlib import Path
import threading
import time
from dataclasses import dataclass
from typing import Any
from core.paths import state_file

PROTECTED = frozenset(x.lower() for x in (
    "system","idle","registry","smss.exe","csrss.exe","wininit.exe",
    "winlogon.exe","services.exe","lsass.exe","lsaiso.exe","svchost.exe",
    "dwm.exe","fontdrvhost.exe","sihost.exe","explorer.exe","taskhostw.exe",
    "audiodg.exe","spoolsv.exe","ctfmon.exe","runtimebroker.exe",
    "securityhealthservice.exe","securityhealthsystray.exe","msmpeng.exe",
    "senseir.exe","mpssvc.exe","nissrv.exe","wscsvc.exe","searchindexer.exe",
    "barq.exe","barq-ai.exe","python.exe","pythonw.exe","py.exe",
    "uvicorn.exe","node.exe","lively.exe","livelycu.exe",
    "ffmpeg.exe","ffprobe.exe","cloudflared.exe","ollama.exe",
    "windows-mcp.exe","openhardwaremonitor.exe","librehardwaremonitor.exe",
    "powershell.exe","pwsh.exe","cmd.exe","conhost.exe",
))
# Conservative allowlist. All other processes require a future audited
# classification rule and stay untouched.
PAUSABLE = frozenset({
    "spotify.exe","epicgameslauncher.exe","steamwebhelper.exe",
    "gog galaxy.exe","battlenet.exe","battle.net.exe",
})
MODES = ("gaming","focus","battery","movie")
_lock = threading.RLock()
_paused: dict[int, dict[str, Any]] = {}
_cpu_samples: dict[tuple[int,float], tuple[float,float]] = {}
_mode = "off"
_timer: threading.Timer | None = None
_expires_at: float = 0.0
_guardian: subprocess.Popen | None = None


def _psutil():
    try:
        import psutil
        return psutil
    except ImportError:
        return None


def _protected_pid_set(psutil) -> set[int]:
    """Protect BARQ and its parent/child process tree regardless of names."""
    selected={os.getpid()}
    try:
        mine=psutil.Process(os.getpid())
        selected.update(p.pid for p in mine.parents())
        selected.update(p.pid for p in mine.children(recursive=True))
    except (psutil.NoSuchProcess,psutil.AccessDenied):
        pass
    return selected


def _visible_window(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    found=[]
    try:
        callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        def callback(hwnd,unused):
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return True
            actual=wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd,ctypes.byref(actual))
            if actual.value==pid:
                found.append(True)
                return False
            return True
        callback_ref=callback_type(callback)
        ctypes.windll.user32.EnumWindows(callback_ref,0)
        return bool(found)
    except (OSError,AttributeError,ValueError):
        # Fail closed: cannot prove absence of unsaved work.
        return True


def _decision(name: str, pid: int, protected: set[int], has_window: bool) -> tuple[str,str]:
    norm=name.lower()
    if pid in protected or norm in PROTECTED:
        return "critical","Protected Windows, security, or BARQ-related process"
    if has_window:
        return "keep","Visible window may contain unsaved work"
    if norm in PAUSABLE:
        return "safe","Recognized optional user application; pauses are reversible"
    return "keep","Not reviewed as safe to pause; no automatic action"


def _processes(psutil, *, limit: int = 160) -> list[dict]:
    protected=_protected_pid_set(psutil)
    now=time.time()
    stamp=time.monotonic()
    output=[]
    for proc in psutil.process_iter(["pid","name","memory_info","create_time","cpu_times"]):
        try:
            info=proc.info
            pid=int(info["pid"])
            name=str(info.get("name") or "Unknown")
            started=float(info.get("create_time") or 0)
            memory=info.get("memory_info")
            timings=info.get("cpu_times")
            seconds=float(getattr(timings,"user",0)+getattr(timings,"system",0)) if timings else None
            key=(pid,started)
            with _lock:
                prev=_cpu_samples.get(key)
                if seconds is not None:
                    _cpu_samples[key]=(stamp,seconds)
            percent=None
            if prev and seconds is not None:
                elapsed=stamp-prev[0]
                if elapsed>=.1 and seconds>=prev[1]:
                    percent=round(min(100.0,100*(seconds-prev[1])/elapsed/max(1,os.cpu_count() or 1)),2)
            visible=_visible_window(pid) if name.lower() in PAUSABLE else False
            risk,reason=_decision(name,pid,protected,visible)
            output.append({
                "pid":pid,"name":name,"publisher":None,
                "ram_mb":round(memory.rss/(1024*1024),1) if memory else None,
                "cpu_percent":percent,
                "uptime_seconds":max(0,round(now-started)) if started else None,
                "classification":risk,"reason":reason,
                "paused":pid in _paused,
            })
        except (psutil.NoSuchProcess,psutil.AccessDenied,psutil.ZombieProcess,ValueError):
            continue
    output.sort(key=lambda x: x["ram_mb"] or 0,reverse=True)
    with _lock:
        if len(_cpu_samples)>2048:
            _cpu_samples.clear()
    return output[:limit]


def snapshot() -> dict:
    psutil=_psutil()
    if not psutil:
        return {"status":"dependency_missing","processes":[],"mode":_mode,
                "paused":[],"note":"Install optional free psutil (BSD-3-Clause) to enable measured process details"}
    with _lock:
        return {"status":"ok","mode":_mode,"modes":list(MODES),
                "processes":_processes(psutil),
                "paused":[{"pid":pid,"name":record["name"]} for pid,record in _paused.items()],
                "auto_modes_enabled":False,
                "note":"CPU needs two samples. Only reviewed optional apps may be paused with explicit approval."}


def _persist() -> bool:
    """Atomic journal, written BEFORE the first suspend; fail closed on disk error."""
    import json
    try:
        path=state_file("resource_saver_paused.json")
        staging=path.with_name(path.name+".tmp")
        staging.write_text(json.dumps({"paused":_paused,"expires_at":_expires_at},
                                      ensure_ascii=False),encoding="utf-8")
        os.replace(staging,path)
        return True
    except OSError:
        return False


def _start_guardian(parent_start:float):
    """Detached process restores approved PIDs on BARQ crash or timeout.

    No elevated rights or generic command execution; refusing to pause if the
    guardian cannot start is safer than leaving background processes frozen.
    """
    global _guardian
    journal=state_file("resource_saver_paused.json")
    if getattr(sys,"frozen",False):
        command=[sys.executable,"--resource-saver-guardian",
                 str(os.getpid()),str(parent_start),str(journal)]
    else:
        command=[sys.executable,"-m","services.resource_saver_guardian",
                 str(os.getpid()),str(parent_start),str(journal)]
    flags=(getattr(subprocess,"CREATE_NO_WINDOW",0)|
           getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)|
           getattr(subprocess,"DETACHED_PROCESS",0))
    try:
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                               cwd=(str(Path(sys.executable).resolve().parent) if getattr(sys,"frozen",False)
                                    else str(Path(__file__).resolve().parents[1])),
                               close_fds=True,creationflags=flags)
        time.sleep(.08)
        if child.poll() is not None:
            raise RuntimeError("Resource-saver recovery guardian exited immediately")
        _guardian=child
    except (OSError,RuntimeError) as exc:
        raise RuntimeError("Could not start separate crash-recovery helper; no apps paused") from exc


def restore_all() -> dict:
    psutil=_psutil()
    restored=[];failures=[]
    with _lock:
        for pid,record in list(_paused.items()):
            try:
                if psutil is None:
                    raise RuntimeError("psutil not installed")
                p=psutil.Process(pid)
                if abs(p.create_time()-record["start"])>=.1:
                    del _paused[pid]
                    continue
                p.resume()
                restored.append(pid)
                del _paused[pid]
            except Exception as exc:
                if psutil is not None and isinstance(exc,(psutil.NoSuchProcess,psutil.ZombieProcess)):
                    _paused.pop(pid,None)
                else:
                    failures.append(pid)
        if not _paused:
            global _mode,_expires_at
            _mode="off"
            _expires_at=0.0
        _persist()
    return {"restored":restored,"failed":failures}


def _recover():
    import json
    global _paused
    try:
        data=json.loads(state_file("resource_saver_paused.json").read_text(encoding="utf-8"))
        with _lock:
            _paused={int(key):value for key,value in data.get("paused",{}).items()}
        restore_all()
    except (OSError,ValueError,TypeError,KeyError):
        pass


def _expire():
    restore_all()


def activate(mode: str, pids: list[int], *, confirmed: bool, seconds: int = 120) -> dict:
    """Pause only verified safe background apps; always auto-resume."""
    global _mode,_timer,_expires_at
    if sys.platform!="win32":
        raise ValueError("Windows desktop required")
    if not confirmed:
        raise PermissionError("Preview and explicitly approve the apps first")
    if mode not in MODES or not 5<=seconds<=300:
        raise ValueError("Unknown mode or duration")
    if len(pids)>12 or not all(type(pid) is int and pid>0 for pid in pids):
        raise ValueError("Invalid process list")
    psutil=_psutil()
    if psutil is None:
        raise RuntimeError("psutil missing")
    protected=_protected_pid_set(psutil)
    selected=[]
    # Validate ENTIRE batch before pausing anything.
    for pid in set(pids):
        try:
            p=psutil.Process(pid)
            name=p.name()
            risk,why=_decision(name,pid,protected,_visible_window(pid))
            if risk!="safe":
                raise PermissionError(f"{name}: {why}")
            selected.append((p,name,p.create_time()))
        except (psutil.NoSuchProcess,psutil.AccessDenied) as exc:
            raise ValueError("The selected process is no longer available") from exc
    # At most one pause group, to keep restore-all predictable.
    with _lock:
        if _paused:
            raise ValueError("Restore the previous mode first")
        try:
            # Record exactly which PIDs and creation times *may* be suspended,
            # BEFORE touching them. A crash at any point can then recover.
            _paused.update({p.pid:{"name":name,"start":started}
                            for p,name,started in selected})
            _expires_at=time.time()+seconds
            if not _persist():
                raise RuntimeError("Cannot write atomic pause journal")
            _start_guardian(psutil.Process(os.getpid()).create_time())
            for p,name,started in selected:
                if p.name().lower() not in PAUSABLE or abs(p.create_time()-started)>=.1:
                    raise PermissionError("Process identity changed")
                p.suspend()
            _mode=mode
            if _timer:
                _timer.cancel()
            _timer=threading.Timer(seconds,_expire)
            _timer.daemon=True
            _timer.start()
        except Exception:
            restore_all()
            raise
    return {"mode":_mode,"paused":[{"pid":p.pid,"name":n} for p,n,_ in selected],
            "auto_restore_seconds":seconds}


_recover()
atexit.register(restore_all)
