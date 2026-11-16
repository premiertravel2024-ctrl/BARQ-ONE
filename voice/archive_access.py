"""Opt-in voice access to saved chats. No unrestricted archive export.

Gemini Live is a cloud service: by default it receives NO other chat history.
Only an explicit settings toggle and a specific voice tool call allow short,
redacted hits, never attachments or raw database dumps.
"""
from __future__ import annotations
import json
import re
import time
from core.paths import state_file

# A Live model can request tools, but cannot independently authorize scanning chats.
# Keep tool results bounded and require a recent user utterance asking to recall chats.
_REQUEST = re.compile(r'(?:شات|محادث|دردشة|فاكر|فكرني|افتكر|اتكلمنا|كلمناك|chat|conversation|history|remember|find)', re.I)
_NEGATED = re.compile(r'(?:ما\s*تدورش|متدورش|متفتحش|بلاش\s*تدور|dont\s+search|do\s+not\s+search)', re.I)

def authorized_spoken_search(last_text: str, last_at: float, *, now: float | None = None) -> bool:
    current=time.monotonic() if now is None else now
    return bool(isinstance(last_text,str) and 0 <= current-last_at <= 25
                and _REQUEST.search(last_text) and not _NEGATED.search(last_text))

SETTINGS_NAME = 'voice_archive_access.json'

def enabled() -> bool:
    try:
        data=json.loads(state_file(SETTINGS_NAME).read_text(encoding='utf-8'))
        return data.get('allow_live_search') is True
    except (OSError, ValueError, TypeError):
        return False

def configure(allow: bool) -> None:
    path=state_file(SETTINGS_NAME)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps({'allow_live_search': bool(allow)}), encoding='utf-8')
    temp.replace(path)

def search(query: str, current_chat_id: str='', limit: int=5, store=None) -> dict:
    if not enabled():
        return {'status':'permission_required', 'message':'بحث المحادثات القديمة مقفول؛ فعّله من إعدادات الصوت بإذنك.'}
    if not isinstance(query,str) or not (2 <= len(query.strip()) <= 100) or any(c in query for c in '\r\n\x00'):
        return {'status':'needs_clarification', 'message':'قول اسم المحادثة أو موضوعها في كلمتين على الأقل.'}
    if store is None:
        from core.history import ConversationStore
        store=ConversationStore()
    from computer_control.safety.policy import redact
    hits=store.search(query,limit=min(max(limit,1),5),exclude_id=current_chat_id)
    return {'status':'ok','matches':[{'id':item['id'],
             'title':redact(item['title'])[:90], 'excerpt':redact(item['excerpt'])[:220]}
             for item in hits],
            'message':'دي نتائج محدودة من محادثاتك المحفوظة. ما أرسلتش مرفقات أو ملفات كاملة.'}


def catalog(limit:int=20,store=None)->dict:
    """List metadata of recent chats only, from the persistent DB. Never export message text."""
    if not enabled():return {'status':'permission_required','message':'فعّل وصول الصوت للمحادثات القديمة من الإعدادات.'}
    if store is None:
        from core.history import ConversationStore
        store=ConversationStore()
    from computer_control.safety.policy import redact
    data=store.list_titles(limit=min(max(int(limit),1),25))
    return {'status':'ok','chats':[{'id':item['id'],'title':redact(item['title'])[:100]} for item in data],
            'message':'دي عناوين المحادثات الأخيرة فقط. تقدر تسألني عن موضوع في كل الشاتات وساعتها هستخدم البحث في الأرشيف.'}
