"""Read-only public GitHub repository discovery for voice and chat.

Search only after a direct user request. Never clone, install, execute, or
transmit chat history to GitHub. Results are bounded and validated.
"""
from __future__ import annotations
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MAX_QUERY=100

def search_repositories(query: str, *, opener=urlopen) -> dict:
    if not isinstance(query,str) or not 2 <= len(query.strip()) <= MAX_QUERY or any(c in query for c in '\r\n\x00'):
        return {'status':'invalid_query','matches':[],'message':'قول اسم الأداة أو نوع المستودع اللي بتدور عليه.'}
    params=urlencode({'q':query.strip(),'per_page':5})
    request=Request('https://api.github.com/search/repositories?'+params,
        headers={'Accept':'application/vnd.github+json','User-Agent':'BARQ-AI-Local-Assistant'})
    try:
        with opener(request,timeout=7) as response:
            data=json.load(response)
    except HTTPError as exc:
        return {'status':'rate_limited' if exc.code in (403,429) else 'unavailable',
                'matches':[],'message':'GitHub رفض البحث مؤقتًا؛ جرّب لاحقًا.'}
    except (URLError,TimeoutError,OSError,ValueError,TypeError):
        return {'status':'unavailable','matches':[],'message':'البحث في GitHub غير متاح حاليًا؛ راجع الاتصال.'}
    if not isinstance(data,dict) or not isinstance(data.get('items'),list):
        return {'status':'unavailable','matches':[],'message':'وصل رد غير صالح من GitHub.'}
    matches=[]
    for entry in data['items'][:12]:
        if not isinstance(entry,dict):continue
        full=entry.get('full_name','')
        if not isinstance(full,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',full):continue
        if entry.get('private') is True:continue
        # Reconstruct the destination from a validated owner/repo; never
        # forward arbitrary html_url returned by an untrusted provider.
        description=entry.get('description')
        matches.append({'repository':full,'url':'https://github.com/'+full,
                        'description':description[:180] if isinstance(description,str) else '',
                        'stars':max(0,min(int(entry.get('stargazers_count') or 0),100000000))})
        if len(matches)==5:break
    return {'status':'ok','matches':matches,'message':'نتائج عامة من GitHub للمراجعة. اختيار مستودع ما بيثبتش كود لوحده.'}


def direct_spoken_search(text: str, when:float, *, now:float) -> bool:
    from voice.repository_context import NEGATED
    if not isinstance(text,str) or not 0 <= now-when <= 20 or NEGATED.search(text):return False
    return bool(re.search(r'(دور|ابحث|فتش|شوف|هات|search|find)',text,re.I) and
                re.search(r'(github|جيت\s*ه[با]|مستودع|مستودعات|ريبو|repo)',text,re.I))


def choice_from_spoken(text:str, when:float, choices:dict[str,str], requested:str, *, now:float) -> str|None:
    """Choose from THIS session's verified search only, for review, never execution."""
    from voice.repository_context import NEGATED, ACTION
    if not isinstance(text,str) or not 0<=now-when<=20 or NEGATED.search(text):return None
    if not (ACTION.search(text) or re.search(r'(هات|اختار|خد|جيب|review|select)',text,re.I)):return None
    name=requested.strip().casefold() if isinstance(requested,str) else ''
    if name not in choices:return None
    # When the search returned multiple hits, the model cannot silently pick
    # any match from a vague "install that" phrase. Require an exact repo name
    # or an ordinal which matches the returned order.
    ordered=list(choices)
    ordinal=re.search(r'(?:الاول|الأول|first|رقم\s*1|number\s*1|التاني|الثاني|second|رقم\s*2|number\s*2|التالت|الثالث|third|رقم\s*3|number\s*3)',text,re.I)
    if ordinal:
        token=ordinal.group(0).casefold()
        index=0 if any(x in token for x in ('اول','أول','first',' 1')) else (1 if any(x in token for x in ('تاني','ثاني','second',' 2')) else 2)
        return choices[name] if index<len(ordered) and ordered[index]==name else None
    if name in text.casefold() or name.split('/')[-1] in text.casefold():return choices[name]
    if len(choices)==1 and re.search(r'(المستودع|الريبو|repo|repository|ده|دا|it)',text,re.I):return choices[name]
    return None
