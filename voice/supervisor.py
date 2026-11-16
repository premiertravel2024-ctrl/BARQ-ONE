"""Bounded, opt-in wake listener recovery for the BARQ desktop process.

Never installs software, kills unrelated processes, changes user preferences,
records microphone audio, or authorizes computer actions. If failures persist,
fail visibly and let the owner intervene instead of looping forever.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable


class WakeSupervisor:
    """Monitor one explicitly enabled wake listener, with a circuit breaker."""

    def __init__(self, enabled: Callable[[], bool], status: Callable[[], dict],
                 restart: Callable[[], tuple[bool, str]],
                 live_active: Callable[[], bool], clock: Callable[[], float] = time.monotonic):
        self.enabled, self.status, self.restart = enabled, status, restart
        self.live_active, self.clock = live_active, clock
        self._failures: deque[float] = deque()
        self._next_attempt = 0.0
        self._phase = 'idle'
        self._detail = ''
        self._guard = threading.RLock()
        self._ready_since = None

    def snapshot(self) -> dict:
        with self._guard:
            now = self.clock()
            return {'state': self._phase, 'detail': self._detail[:160],
                    'restart_attempts': len(self._failures),
                    'retry_after_seconds': max(0, round(self._next_attempt - now))}

    def check_once(self) -> str:
        """One safe inspection, no raw audio or user text captured."""
        with self._guard:
            now = self.clock()
            if not self.enabled():
                self._phase, self._detail = 'disabled', ''
                self._failures.clear()
                self._next_attempt = 0
                self._ready_since = None
                return self._phase
            if self.live_active():
                self._phase = 'in_call'
                self._detail = 'المستمع متوقف مؤقتًا لصالح مكالمة برق'
                return self._phase
            state = self.status()
            if state.get('running') and state.get('state') in ('listening','loading','starting','waiting','activated'):
                self._phase = 'healthy'
                self._detail = ''
                if self._ready_since is None: self._ready_since = now
                # Only stable operation resets the restart budget.
                if now - self._ready_since >= 120:
                    self._failures.clear()
                return self._phase
            self._ready_since = None
            # An explicitly stopped or unavailable audio engine should not be
            # blindly restarted if the model/runtime is missing or permissions fail.
            detail = str(state.get('detail') or '')[:160]
            if state.get('state') == 'error' and any(word in detail.casefold() for word in
                    ('access denied','permission','not available','not installed','غير موجود','missing','unavailable')):
                self._phase, self._detail = 'needs_attention', detail
                return self._phase
            while self._failures and now - self._failures[0] >= 300:
                self._failures.popleft()
            if len(self._failures) >= 3:
                self._phase = 'needs_attention'
                self._detail = 'تكرار فشل الميكروفون؛ اضغط إعادة تشغيل الاستماع من الإعدادات بعد مراجعة الجهاز'
                return self._phase
            if now < self._next_attempt:
                self._phase = 'cooldown'
                return self._phase
            self._failures.append(now)
            ok, message = self.restart()
            self._next_attempt = now + min(60, 5 * 2 ** (len(self._failures) - 1))
            self._phase = 'recovering' if ok else 'cooldown'
            self._detail = (message or 'محاولة استعادة الاستماع')[:160]
            return self._phase

    def run(self, stop: threading.Event, interval: float = 5) -> None:
        while not stop.is_set():
            try:
                self.check_once()
            except Exception as exc:
                # Do not let a monitoring exception crash the assistant.
                with self._guard:
                    self._phase = 'monitor_error'
                    self._detail = type(exc).__name__
            stop.wait(interval)
