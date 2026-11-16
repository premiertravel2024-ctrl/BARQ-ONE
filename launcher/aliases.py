"""Bundled/user local labels; only pinned HTTPS destinations are opened."""
from __future__ import annotations
from pathlib import Path
import difflib,re,yaml
from core.paths import resource,state_file
from .nlu import clean

def catalog() -> dict:
    original=yaml.safe_load(resource('config','app_aliases.yaml').read_text(encoding='utf-8')) or {}
    custom=state_file('app_aliases.user.yaml')
    if custom.is_file():
        try:
            data=yaml.safe_load(custom.read_text(encoding='utf-8')) or {}
            for app,aliases in (data.get('apps') or {}).items():
                if isinstance(app,str) and isinstance(aliases,list) and len(aliases)<=50:
                    original.setdefault('apps',{}).setdefault(app,[]).extend(str(x)[:100] for x in aliases)
        except (OSError,ValueError,yaml.YAMLError):pass
    return original

def _ar_name_forms(value: str) -> set[str]:
    """Normalize optional Egyptian Arabic definite articles in app names."""
    name = clean(value)
    forms = {name}
    if name.startswith('ال') and len(name) >= 5:
        forms.add(name[2:])
    if name.startswith('بال') and len(name) >= 6:
        forms.add(name[3:])
    return {form for form in forms if form}


def alias_target(target: str, mapping: dict[str, list[str]]) -> list[tuple[str, float]]:
    names = _ar_name_forms(target)
    scored = []
    for canonical, variants in mapping.items():
        forms = [clean(canonical)] + [clean(value) for value in variants]
        if any(name in forms for name in names):
            score = 1.0
        else:
            score = max((difflib.SequenceMatcher(None, name, form).ratio()
                         for name in names for form in forms if form), default=0)
            if any(name and name in form.split() for name in names for form in forms):
                score = max(score, .91)
        if score >= .60:
            scored.append((canonical, score))
    return sorted(scored, key=lambda item: -item[1])
