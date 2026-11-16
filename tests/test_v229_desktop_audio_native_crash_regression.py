"""Regression tests for a Windows native GUI crash after multiple voice replies.

The Win32 window class owns a WNDPROC callback. Never create a fresh owner
per sentence while leaving the old class registered in the OS.
"""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock


def test_glow_keeps_one_callback_alive_across_multiple_turns(monkeypatch):
    import voice.screen_glow as glow
    events = ['speaking', 'quiet', 'speaking', 'quiet', 'speaking', 'quiet']
    made = []

    class FakeGlow:
        def __init__(self):
            self.shown = 0
            self.removed = 0
            self.closed = 0
            made.append(self)
        def show(self, _): self.shown += 1
        def remove_windows(self): self.removed += 1
        def pump(self): pass
        def close(self): self.closed += 1

    class FakeStop:
        def __init__(self): self.index=0
        def is_set(self): return self.index >= len(events)
        def wait(self,_seconds): self.index += 1

    stop=FakeStop()
    monkeypatch.setattr(glow,'os',SimpleNamespace(name='nt'))
    monkeypatch.setattr(glow,'_WindowsGlow',FakeGlow)
    glow.run_glow(stop,lambda: events[stop.index]=='speaking')
    assert len(made)==1, 'Callback lifetime must span all speech transitions'
    assert made[0].shown==3
    assert made[0].removed==3
    assert made[0].closed==1


def test_native_glow_registers_and_unregisters_window_class():
    root=Path(__file__).resolve().parents[1]
    text=(root/'voice'/'screen_glow.py').read_text(encoding='utf-8')
    assert 'UnregisterClassW(self.class_name, self.instance)' in text
    assert 'CreateSolidBrush.restype = wintypes.HBRUSH' in text
    assert 'DeleteObject.argtypes = [wintypes.HGDIOBJ]' in text


def test_fatal_desktop_crash_trace_enabled():
    source=(Path(__file__).resolve().parents[1]/'desktop.py').read_text(encoding='utf-8')
    assert "faulthandler.enable(file=_crash_stream, all_threads=True)" in source
    assert "'desktop-crash.log'" in source
