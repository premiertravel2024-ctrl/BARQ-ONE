"""BARQ automation alarms: local-only persistence and Windows notifications.

Clock alarms fire only while the BARQ backend is running (including its tray mode).
No system-wide tasks, arbitrary commands, or remote notifications are created.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

from core.paths import state_file

_LOCK = threading.RLock()
_STARTED = False
_STOP = threading.Event()
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_FILE = "barq-alarms.json"


def _path() -> Path:
    return state_file(_FILE)


def _read() -> list[dict]:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(value, list):
            return [item for item in value[:30] if isinstance(item, dict)]
    except (OSError, ValueError):
        pass
    return []


def _write(entries: list[dict]) -> None:
    path = _path()
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as file:
            json.dump(entries, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def alarms() -> list[dict]:
    with _LOCK:
        return _read()


def create_alarm(when: str, label: str, repeat: bool) -> dict:
    if not _TIME_RE.fullmatch(when):
        raise ValueError("وقت المنبّه لازم يكون بالشكل HH:MM.")
    label = label.strip()
    if not 1 <= len(label) <= 70:
        raise ValueError("عنوان المنبّه لازم يكون بين حرف و70 حرف.")
    with _LOCK:
        entries = _read()
        if len(entries) >= 30:
            raise ValueError("الحد الأقصى 30 منبّه.")
        alarm = {"id": uuid.uuid4().hex, "time": when, "label": label,
                 "repeat": bool(repeat), "enabled": True, "last_fired": ""}
        entries.append(alarm)
        _write(entries)
        return alarm


def toggle_alarm(identifier: str, enabled: bool) -> dict:
    with _LOCK:
        entries = _read()
        for item in entries:
            if item.get("id") == identifier:
                item["enabled"] = bool(enabled)
                _write(entries)
                return item
        raise KeyError("المنبّه مش موجود.")


def delete_alarm(identifier: str) -> bool:
    with _LOCK:
        entries = _read()
        filtered = [item for item in entries if item.get("id") != identifier]
        if len(filtered) == len(entries):
            return False
        _write(filtered)
        return True


def _notify(label: str) -> None:
    """Only a user-created scheduled alarm can call this. No shell used."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except (ImportError, OSError):
        pass
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, label, "BARQ ONE · المنبّه", 0x40 | 0x1000)
        except (AttributeError, OSError):
            pass


def tick(now: datetime | None = None, notify=_notify) -> int:
    """Run one check. A single minute never triggers the same alarm twice."""
    now = now or datetime.now().astimezone()
    marker = now.strftime("%Y-%m-%d %H:%M")
    due = []
    with _LOCK:
        entries = _read()
        dirty = False
        for alarm in entries:
            if not alarm.get("enabled") or alarm.get("time") != marker[-5:] or alarm.get("last_fired") == marker:
                continue
            alarm["last_fired"] = marker
            if not alarm.get("repeat"):
                alarm["enabled"] = False
            due.append(str(alarm.get("label") or "منبّه"))
            dirty = True
        if dirty:
            _write(entries)
    for label in due:
        threading.Thread(target=notify, args=(label,), daemon=True).start()
    return len(due)


def _loop() -> None:
    while not _STOP.is_set():
        try:
            tick()
        except (OSError, ValueError):
            pass
        _STOP.wait(15)


def start() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
        _STOP.clear()
        threading.Thread(target=_loop, name="barq-alarms", daemon=True).start()


def stop() -> None:
    global _STARTED
    with _LOCK:
        _STOP.set()
        _STARTED = False
