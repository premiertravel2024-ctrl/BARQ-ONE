"""Resolve human-readable Windows app names using installed-app metadata.

No arbitrary shell strings, automatic downloads or remote actions.
"""
from __future__ import annotations
from functools import lru_cache
import time
from computer_control.cognition import _norm

ALIASES={
    'notepad': ('notepad','المفكره','المفكرة','نوت باد'),
    'calc': ('calculator','حاسبه','الحاسبه','اله حاسبه','الالة الحاسبة','calc'),
    'msedge': ('edge','ايدج','مايكروسوفت ايدج','msedge'),
    'chrome': ('chrome','كروم','جوجل كروم','google chrome'),
    'explorer': ('explorer','مستكشف الملفات','فايل اكسبلورر'),
    'mspaint': ('paint','الرسام','رسام'),
    'code': ('vscode','vs code','في اس كود','فيجوال ستوديو كود'),
}

BUILTIN={'notepad':'notepad.exe','calc':'calc.exe','explorer':'explorer.exe','mspaint':'mspaint.exe'}


def normalized_app(name: str) -> str:
    n=_norm(name)
    for canonical, forms in ALIASES.items():
        if n==_norm(canonical) or n in {_norm(x) for x in forms}:
            return canonical
    return n

@lru_cache(maxsize=1)
def _apps_cached():
    from launcher.indexes import Index
    return time.monotonic(),Index().apps()


def resolve_app(name: str) -> dict | None:
    """Resolve a unique installed app; ambiguous matches are rejected.

    Cache is short-lived to detect new installations during a BARQ session.
    """
    canonical=normalized_app(name)
    if canonical in BUILTIN:return {'path':BUILTIN[canonical]}
    refreshed,apps=_apps_cached()
    if time.monotonic()-refreshed>90:
        _apps_cached.cache_clear()
        _,apps=_apps_cached()
    matches=[p for p in apps if normalized_app(p.get('label',''))==canonical]
    if not matches:return None
    # Multiple identical entries of the same target are okay; different targets
    # must be resolved by the user rather than arbitrary first-match.
    by_target={(e.get('appid') or e.get('path')):e for e in matches if e.get('appid') or e.get('path')}
    if len(by_target)!=1:raise ValueError('Multiple installed applications match; specify exact app')
    return next(iter(by_target.values()))
