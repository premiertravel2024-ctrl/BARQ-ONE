"""A single BARQ desktop process survives closing its window via the Windows tray.

The user explicitly enables the wake microphone in BARQ settings. Merely
minimizing to tray does not open a cloud Live conversation or grant tools.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

_active: 'BackgroundWindow | None' = None


class BackgroundWindow:
    def __init__(self, window: Any, image_path: Path, *, start_hidden: bool = False):
        self.window = window
        self.image_path = image_path
        self.start_hidden = start_hidden
        self.quit_requested = False
        self.tray = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._first_show = True

    def start(self) -> bool:
        """Do not hijack close if no working tray can be created."""
        if sys.platform != 'win32':
            return False
        try:
            import pystray
            from PIL import Image
            icon_image = Image.open(self.image_path).convert('RGBA')
            self.tray = pystray.Icon('barq-integrated', icon_image, 'برق — مستنيك', menu=pystray.Menu(
                pystray.MenuItem('افتح برق', self.open, default=True),
                pystray.MenuItem('إيقاف الاستماع', self.pause),
                pystray.MenuItem('استئناف الاستماع', self.resume),
                pystray.MenuItem('إيقاف فوري للصوت والتنفيذ',lambda *args: __import__('services.assistant_runtime',fromlist=['request_stop']).request_stop()),
                pystray.MenuItem('إغلاق برق نهائيًا', self.exit),
            ))
            def run_icon():
                try:
                    self.tray.run(setup=lambda icon: self._ready.set())
                finally:
                    self._ready.set()
            self._thread = threading.Thread(target=run_icon, name='BARQ-Tray', daemon=True)
            self._thread.start()
            if not self._ready.wait(timeout=5) or not self._thread.is_alive():
                try: self.tray.stop()
                except Exception: pass
                return False
            self.window.events.closing += self.on_closing
            if self.start_hidden:
                self.window.events.shown += self.on_shown
            return True
        except (ImportError, OSError, RuntimeError) as exc:
            print(f'BARQ integrated tray disabled: {type(exc).__name__}', file=sys.stderr)
            return False

    def on_shown(self):
        if self._first_show and self.start_hidden:
            self._first_show = False
            self.window.hide()

    def on_closing(self) -> bool:
        """X hides the window; it must not end BARQ's active session.

        The wake listener and local server belong to the desktop process, not
        to the WebView window. The tray's explicit Exit is the only UI action
        which requests shutdown. Never interrupt an active live conversation on a window hide.
        """
        if self.quit_requested:
            return True
        try:
            self.window.hide()
        except Exception as exc:
            print(f'BARQ tray hide failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return False

    def open(self, *unused):
        try:
            self.window.show()
            self.window.restore()
        except Exception:
            pass

    def pause(self, *unused):
        # Disabling first prevents the supervisor racing the stop.
        from voice.wake import set_wake_enabled_from_tray, stop_listener
        set_wake_enabled_from_tray(False)
        stop_listener()
        try:
            self.window.evaluate_js("window.dispatchEvent(new Event('barq-handsfree-stop'))")
        except Exception:
            pass

    def resume(self, *unused):
        from voice.wake import set_wake_enabled_from_tray, start_listener
        set_wake_enabled_from_tray(True)
        start_listener()

    def exit(self, *unused):
        self.quit_requested = True
        from voice.wake import stop_listener
        stop_listener()
        try:
            if self.tray: self.tray.stop()
        finally:
            try: self.window.destroy()
            except Exception: pass

    def stop(self):
        self.quit_requested = True
        if self.tray:
            try: self.tray.stop()
            except Exception: pass


def install(window: Any, image_path: Path, *, start_hidden: bool = False) -> bool:
    global _active
    controller = BackgroundWindow(window, image_path, start_hidden=start_hidden)
    if not controller.start():
        return False
    _active = controller
    return True


def show_on_wake() -> None:
    """Called only after the local wake detector has authenticated a signal."""
    if _active is not None:
        try:
            from voice.wake import wake_preferences
            if wake_preferences().get('show_on_wake',False):_active.open()
            else:_active.window.evaluate_js("window.dispatchEvent(new Event('barq-native-wake'))")
        except Exception:_active.open()


def notify(message):
    if _active is not None and _active.tray:_active.tray.notify(message,'برق')


def stop_output():
    if _active is not None:
        try:_active.window.evaluate_js("window.dispatchEvent(new Event('barq-handsfree-stop'));window.speechSynthesis?.cancel()")
        except Exception:pass


def shutdown() -> None:
    global _active
    if _active is not None:
        _active.stop()
    _active = None
