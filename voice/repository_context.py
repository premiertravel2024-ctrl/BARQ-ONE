"""Voice/typed GitHub context handoff: classify and preview, never auto-install.

This module never invokes a repository subprocess or downloads code.  Only
links written directly by the user are resolved as conversational context.
A new, positive spoken request is always necessary to prepare a handoff.
"""
from __future__ import annotations
import re
import time
from github.repositories import parse_url, RepositoryError

LINK = re.compile(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?(?=$|[\s\]>)،,.;!?؟])', re.I)
ACTION = re.compile(r'(?:نزل(?:ه|ها|لي)?|نزّل(?:ه|ها|لي)?|حمّل(?:ه|ها|لي)?|حمل(?:ه|ها|لي)?|ثبت(?:ه|ها|لي)?|ثبّت(?:ه|ها|لي)?|استورد(?:ه)?|استخدم(?:ه|ها)?|خد(?:ه)?|اشتغل\s+عليه|اشتغل\s+على\s+(?:ده|دا|المستودع|الريبو)|تنزل(?:ه|ها)?|تثبت(?:ه)?|تستخدم(?:ه)?|افتح(?:ه)?|جهز(?:ه)?|ضيف(?:ه)?|download|clone|import|install|use\s+(?:it|the\s+repo)|set\s+up)', re.I)
REFERENCE = re.compile(r'(?:github|جيت\s*هب|مستودع|الريبو|الريبوزيتوري|الرابط|اللينك|ده|دا|دي|اللي\s+بعت|عليه|it|repo|repository|link)', re.I)
NEGATED = re.compile(r'(?:متنزلش|متثبتش|متعملش|ما\s*تنزلش|ما\s*تثبتش|لا\s+(?:تنزل|تثبت|تستخدم|تستورد)|do\s+not|don.t|لو\s+قلت|افترض|كمثال|hypothetical)',re.I)
MAX_AGE=20.0

def last_user_repository(messages: list[dict]) -> str | None:
    """Never take a link from assistant messages, files, tool output or prompts."""
    if not isinstance(messages,list): return None
    for msg in reversed(messages[-16:]):
        if not isinstance(msg,dict) or msg.get('role')!='user': continue
        content=msg.get('content','')
        if not isinstance(content,str): continue
        for match in reversed(list(LINK.finditer(content[:2400]))):
            try:
                owner, repo, _=parse_url(match.group(0))
            except RepositoryError: continue
            return f'https://github.com/{owner}/{repo}'
    return None

def prepare_spoken_repository(transcript: str, when: float, previous_url: str | None, now: float | None=None) -> dict:
    """A speech command can request a preview, never permission to execute code."""
    moment=time.monotonic() if now is None else now
    if not transcript or not isinstance(transcript,str) or moment-when>MAX_AGE or moment<when:
        return {'status':'needs_clarification','message':'ما وصلنيش طلب صوتي حديث وواضح.'}
    message=transcript.strip()[:420]
    if NEGATED.search(message):
        return {'status':'denied','message':'الكلام ده نفي أو مثال، مش أمر استيراد.'}
    direct=last_user_repository([{'role':'user','content':message}])
    # With a recent user-shared link, an imperative pronoun ("ثبته") is
    # grounded enough for a *preview*, not for execution. Without the link
    # it is ambiguous and must never fabricate a repository target.
    anaphoric=bool(previous_url and re.fullmatch(
        r'(?:يا\s+برق\s+)?(?:نزله|نزّل[ه]?|حمله|حمّله|ثبته|ثبّت[ه]?|استورده|استخدمه|جهزه|جهزهولي|اشتغل\s+عليه)[.!؟?\s]*', message, re.I))
    if not direct and not (ACTION.search(message) and REFERENCE.search(message)) and not anaphoric:
        return {'status':'needs_clarification','message':'قول لي تستخدم أي مستودع من GitHub، أو ابعت رابطه في الشات.'}
    if direct and previous_url and direct != previous_url:
        # User explicitly supplied a new URL; this is authoritative for preview,
        # not permission to download. It must still be shown for approval.
        url=direct
    else:
        url=direct or previous_url
    if not url:
        return {'status':'needs_clarification','message':'ابعت رابط GitHub في الشات الأول، وبعدها قولي استخدمه.'}
    try:
        owner, repo, _=parse_url(url)
    except RepositoryError:
        return {'status':'denied','message':'رابط المستودع مش صالح.'}
    return {'status':'preview_ready','url':f'https://github.com/{owner}/{repo}',
            'message':f'وصلني مستودع {owner}/{repo}. فتحته للمراجعة في مساحة العمل؛ التنزيل أو التثبيت مش هيبدأ قبل موافقتك من الشاشة.'}
