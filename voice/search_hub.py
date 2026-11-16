"""BARQ session-local search routing. Public queries and device metadata never mix.

Inspired by OpenJarvis tool-resolution (one verified tool per user intent), but
uses BARQ's existing consent gates and data providers. Search results and
ordinals exist only in RAM for the duration of the current voice session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Callable, Awaitable

from voice.command_guard import normalize

_DURATION = 180.0
_ORDINALS = {'الاول': 0, 'اول': 0, 'first': 0, 'رقم 1': 0,
             'التاني': 1, 'الثاني': 1, 'second': 1, 'رقم 2': 1,
             'التالت': 2, 'الثالث': 2, 'third': 2, 'رقم 3': 2,
             'الرابع': 3, 'fourth': 3, 'رقم 4': 3, 'الخامس': 4, 'fifth': 4}
_PRIVATE_WEB = re.compile(r'(?:كلمة\s*السر|password|api[\s_-]*key|token|secret|\b(?:c:\\|[a-z]:\\)|ملف\s*(?:عندي|بتاعي|عندنا)|محادثات[ي]?|شاتات[ي]?|بريد[ي]?|ايميل[ي]?)',re.I)


def classify_scope(text: str, explicit: str = '') -> str:
    """Deterministic privacy-aware resolver; no LLM decisions grant access."""
    value = normalize(text)
    if re.search(r'(?:شات|محادث|دردش|conversation|chat history)', value):return 'chats'
    local = re.search(r'(?:جهازي|عندي|الجهاز|الكمبيوتر|الهارد|ديسكتوب|my (?:pc|computer|files))', value)
    if local and re.search(r'(?:فيلم|افلام|movies|الفيديوهات|video)', value):return 'media'
    if local or re.search(r'(?:ملف|مجلد|فايل|فولدر|pdf|\bfile\b|folder)',value) or re.search(r'(?i)[a-z]:[\\/]|\.(?:xlsx?|docx?|pptx?|csv|zip)\b',text):
        if not re.search(r'\b(?:ملف|مجلد|فايل|فولدر|file|folder)\b',value) and re.search(r'(?:حرار.*(?:معالج|كارت|جهاز)|cpu temp|gpu temp|رام|البطاري|ram usage|مواصفات)',value):
            return 'facts'
        return 'device'
    if re.search(r'(?:github|جيت\s*ه[با]|مستودع|ريبو|repository)', value):return 'github'
    if re.search(r'(?:حرار.*(?:معالج|كارت|جهاز)|cpu temp|gpu temp|رام|البطاري|ram usage|مواصفات)',value):return 'facts'
    if re.search(r'(?:طقس|الجو|weather|درجة\s*حرارة\s*في)',value):return 'weather'
    # A proposed scope is never allowed to turn a private intent into web search.
    if explicit in {'web','device','github','chats','media','weather','facts'}:
        if explicit == 'web' and _PRIVATE_WEB.search(text):return 'blocked_private'
        return explicit
    return 'web'


def _query(text: str) -> str:
    from voice.intent import command_target, command_text
    words = command_text(text).split()
    if words and words[0] in {'دور','ابحث','فتش','شوف','فين','هات','find','search'}:
        target = re.sub(r'^(?:على|علي|ع|عن|for)\s+', '', command_target(text), flags=re.I)
        return target[:160].strip()
    return text.strip()[:160]



def _ordinal(text: str):
    value=normalize(text).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789'))
    if match:=re.search(r'(?<!\w)رقم ([1-9]|10)(?!\w)',value):return int(match[1])-1
    for word,index in _ORDINALS.items():
        if re.search(r'(?<!\w)'+re.escape(normalize(word))+r'(?!\w)',value):return index
    return None


@dataclass
class SearchHub:
    """Results retained in the current process, never a persistent search log."""
    items: list[dict] = field(default_factory=list)
    scope: str = ''
    at: float = 0.0
    now: Callable[[], float] = time.monotonic

    def remember(self, scope: str, items: list[dict]) -> None:
        self.scope = scope
        self.items = [{k:v for k,v in item.items() if k in {'label','kind','url','id','extension','description'}}
                      for item in items[:10] if isinstance(item,dict)]
        self.at = self.now()

    def select(self, spoken: str) -> dict:
        index=_ordinal(spoken)
        if self.now()-self.at > _DURATION or not self.items:
            return {'status':'expired','message':'نتائج البحث القديمة انتهت. قول لي أدور على إيه تاني.'}
        if index is None or index >= len(self.items):
            return {'status':'needs_clarification','message':'حدد رقم نتيجة موجودة؛ مش هفتح حاجة بالتخمين.'}
        return {'status':'selected','item':self.items[index], 'index': index}

    async def search(self, text: str, *, scope: str = '', computer_enabled: bool,
                     local_dispatch=None, web_dispatch=None, github_dispatch=None,
                     chat_dispatch=None) -> dict:
        target=classify_scope(text,scope)
        if scope=='web' and _PRIVATE_WEB.search(text):target='blocked_private'
        if target=='blocked_private':
            return {'status':'denied','message':'مش هبعت معلومات ملفاتك أو الشات للبحث العام.'}
        query=_query(text)
        if target=='device':
            query=re.sub(r'(?i)^(?:ملف|ملفات|مجلد|مجلدات|فولدر|فايل|file|files|folder)\s+','',query).strip(' ،؟')
            query=re.sub(r'\s+(?:(?:على|علي|ع|في|جوا|داخل)\s+(?:ال)?(?:جهاز|كمبيوتر|هارد)\w*|عندي)(?:\s+لو سمحت)?[.؟]?$', '',query).strip()
        elif target=='github':
            query=re.sub(r'(?i)(?:github|جيت\s*ه[با]|مستودع|مستودعات|ريبو)','',query).strip(' ،.؟') or query
        elif target=='weather':
            query=re.sub(r'(?i)^(?:الطقس|الجو|حالة الجو|weather|درجة الحرارة)\s*(?:في|بـ|ب)?\s*','',query).strip(' ،.؟') or query
        if target in {'device','media','facts'}:
            if target != 'facts' and not computer_enabled:
                return {'status':'disabled','message':'فعّل إذن الكمبيوتر والصوت من إعدادات برق الأول.'}
            if local_dispatch is None:
                from voice.computer_tools import dispatch_computer_tool
                local_dispatch=dispatch_computer_tool
            name={'device':'search_device_files','media':'find_local_movies','facts':'get_pc_system_facts'}[target]
            args={'query':query} if target!='facts' else {'question':text}
            result=await local_dispatch(name,args)
        elif target == 'chats':
            # Never expose saved-chat content without separate archive consent.
            from voice.archive_access import enabled, search
            if not enabled():return {'status':'permission_required','message':'فعّل البحث في الشاتات القديمة من إعدادات برق الصوتي.'}
            if chat_dispatch is None:
                import asyncio
                result=await asyncio.to_thread(search,query)
            else:result=await chat_dispatch(query)
        elif target=='github':
            if github_dispatch is None:
                import asyncio
                from services.github_discovery import search_repositories
                result=await asyncio.to_thread(search_repositories,query)
            else:result=await github_dispatch(query)
        elif target=='weather':
            if web_dispatch is None:
                import asyncio
                from services.public_hub import lookup,describe
                result=await asyncio.to_thread(lookup,'weather_forecast',query)
                if result.get('status')=='ok':result['message']=describe(result)
            else:result=await web_dispatch(query,'weather')
        else:
            if _PRIVATE_WEB.search(query):
                return {'status':'denied','message':'البحث العام مينفعش يشمل ملفات خاصة أو كلمات سر.'}
            if web_dispatch is None:
                from services.web_research import research_async
                result=await research_async(query,timeout=9)
            else:result=await web_dispatch(query,'web')
        if not isinstance(result,dict):return {'status':'unavailable','message':'محرك البحث رجّع بيانات غير صالحة.'}
        hits=result.get('results') or result.get('matches') or result.get('movies') or []
        cards=[]
        for match in hits[:10]:
            if not isinstance(match,dict):continue
            title=str(match.get('name') or match.get('title') or match.get('repository') or match.get('label') or '')[:120]
            if not title:continue
            card={'label':title,'kind':target}
            if isinstance(match.get('id'),str):card['id']=match['id']
            if target in {'web','github'}:
                url=match.get('url','')
                if isinstance(url,str) and url.startswith('https://') and len(url)<600:card['url']=url
                if target=='github' and isinstance(match.get('description'),str):card['description']=match['description'][:150]
            if target=='device' and isinstance(match.get('extension'),str):card['extension']=match['extension'][:12]
            cards.append(card)
        if result.get('status')=='ok':self.remember(target,cards)
        if target in {'device','facts','weather'} and (target!='device' or result.get('status')!='ok'):
            self.remember(target,[])
        return {'status':result.get('status','unavailable'),
                'message':result.get('message','لقيت النتائج المتاحة.' if cards else 'مفيش نتائج مؤكدة.'),
                'cards':cards,'count':len(cards),'scope':target}

    async def followup(self, spoken: str, *, opener: Callable[[dict], Awaitable[dict]] | None = None) -> dict:
        chosen=self.select(spoken)
        if chosen['status']!='selected':return chosen
        item=chosen['item']; word=normalize(spoken)
        if any(s in word for s in ('الاحدث','احدث','newest')):
            return {'status':'needs_clarification','message':'نتائج البحث مش معاها تواريخ مؤكدة للترتيب.'}
        if any(s in word for s in ('افتح','شغل','open')):
            if opener is None:return {'status':'needs_approval','message':'اختار النتيجة من واجهة برق لفتحها بأمان.','cards':[item]}
            return await opener(item)
        # Read only metadata; no raw file contents and no external uploads.
        if any(s in word for s in ('اقرا','اقرأ','read')):
            return {'status':'selected','message':'النتيجة المختارة: '+item['label']+'؛ قراءة محتوى الملفات تحتاج إذن صريح داخل برق.', 'cards':[item]}
        return {'status':'selected','message':'اخترت '+item['label']+'؛ قول افتحها لو عايزني أفتحها.', 'cards':[item]}
