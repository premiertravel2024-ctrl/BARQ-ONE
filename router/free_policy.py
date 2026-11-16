"""Immutable bundled free allowlist and billing-kill-switch state (no API calls)."""
from __future__ import annotations
import json,re
from functools import lru_cache
from pathlib import Path
import yaml
from core.paths import resource, state_file

@lru_cache(maxsize=1)
def bundle_policy():
    data=yaml.safe_load(resource('config','free_allowlist.yaml').read_text(encoding='utf-8'))
    return ({name:frozenset(values) for name,values in data['allow'].items()}, frozenset(data['block']))

def permitted(provider,model):
    allow,blocked=bundle_policy()
    return bool(model not in blocked and model in allow.get(provider,()) and
                (provider!='openrouter' or model=='openrouter/free' or model.endswith(':free')))

BILLING_RE=re.compile(r'\b(?:payment\s+(?:required|method)|billing|insufficient\s+credits?|buy\s+credits?|upgrade\s+(?:your\s+)?plan|paid\s+plan|credits?\s+exhausted|quota\s+requires\s+payment)\b',re.I)
def is_billing(status=None,message=''):
    return status==402 or bool(BILLING_RE.search(str(message)[:700]))

def read_blocks():
    path=state_file('provider_billing_blocks.json')
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (FileNotFoundError,ValueError,OSError):return {}

def blocked(name):return bool(read_blocks().get(name))

def set_block(name,enabled=True):
    from router.config import bundled_providers
    if name not in bundled_providers():raise ValueError('Unknown provider')
    data=read_blocks()
    if enabled:data[name]={'billing_blocked':True,'reason_ar':'تم إيقاف المزود بسبب طلب دفع أو رصيد مدفوع'}
    else:data.pop(name,None)
    path=state_file('provider_billing_blocks.json')
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def note_billing(name,status=None,message=''):
    if is_billing(status,message):
        set_block(name)
        return True
    return False
