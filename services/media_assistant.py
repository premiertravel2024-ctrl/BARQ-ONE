"""Local movie search -> real candidates -> exact playback, shared by chat/voice."""
from __future__ import annotations
import asyncio
from collections import OrderedDict
from pathlib import Path
import re
import time
from voice.command_guard import normalize
from voice.intent import non_executable
from services.local_media import discover_movies,EXTENSIONS
from computer_control.safety.policy import sensitive

_LOCAL=re.compile(r'جهاز|هارد|الكمبيوتر|عندي|my (?:pc|computer|drive)',re.I)
_MEDIA=re.compile(r'فيلم|افلام|movie|video|فيديو',re.I)
_ACTION=re.compile(r'دور|ابحث|رشح|اختار|شوف|شغل|افتح|find|recommend|choose|play|show',re.I)
_PLAY=re.compile(r'شغل|شغله|افتح|play|watch',re.I)
_RECOMMEND=re.compile(r'حلو|جامد|رشح|اختار|recommend|choose',re.I)
_ORDINALS={'الاول':0,'اول':0,'first':0,'التاني':1,'الثاني':1,'second':1,'التالت':2,'الثالث':2,'third':2,'الرابع':3,'fourth':3}


class MediaAssistant:
    def __init__(self,*,clock=time.monotonic,discovery=discover_movies,manager_factory=None,policy_loader=None):
        self.clock=clock;self.discovery=discovery;self.manager_factory=manager_factory;self.policy_loader=policy_loader
        self.items=[];self.at=0.0;self.selected=0;self.lock=asyncio.Lock()

    def matches(self,text:str)->bool:
        if not isinstance(text,str) or len(text)>600 or non_executable(text):return False
        value=normalize(text)
        if _LOCAL.search(value) and _MEDIA.search(value) and _ACTION.search(value):return True
        return bool(self.items and self.clock()-self.at<180 and (
            re.search(r'^(?:شغل(?:لي|ه|لي التاني)?|افتح)\s*(?:الفيلم|الاول|التاني|الثاني|التالت|الثالث|اللي رشحته|ده|دا|first|second)?$',value)
            or value in ('غيره','فيلم تاني','اختار غيره','شغل غيره')))

    def _policy(self):
        if self.policy_loader:return self.policy_loader()
        from computer_control.api import load_policy
        return load_policy()

    def _manager(self):
        if self.manager_factory:return self.manager_factory()
        from computer_control.api import manager
        return manager()

    def cards(self):
        return [{'label':item['name'],'kind':'media','description':item.get('quality','')+' — '+str(item.get('size_gb',''))+' GB'} for item in self.items[:7]]

    async def command(self,text:str,*,source='text')->dict:
        if not self.matches(text):return {'matched':False}
        async with self.lock:
            policy=self._policy()
            if not policy.enabled:return {'matched':True,'status':'disabled','message':'فعّل تحكم برق في الكمبيوتر مرة واحدة من الإعدادات.','cards':[]}
            value=normalize(text)
            fresh=bool(_LOCAL.search(value) and _MEDIA.search(value))
            if fresh:
                title=re.search(r'(?:اسمه|بعنوان|called|named)\s+(.+?)(?:\s+(?:وشغله|وافتحه|and play it))?$',text,re.I)
                query=title.group(1).strip()[:120] if title else ''
                query=re.sub(r'\s+(?:على|علي|ع|في|من)\s+(?:ال)?(?:جهاز|كمبيوتر|هارد)\w*.*$', '',query).strip(' \"\'')
                result=await asyncio.to_thread(self.discovery,policy.allowed_folders,query=query,include_paths=True)
                self.items=[];self.at=self.clock();self.selected=0
                for movie in result.get('movies',[])[:12]:
                    try:
                        path=Path(movie['_path']).resolve(strict=True)
                        if not path.is_file() or path.suffix.lower() not in EXTENSIONS or sensitive(str(path)):continue
                        stat=path.stat()
                        self.items.append({**movie,'_path':str(path),'_identity':(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)})
                    except (KeyError,OSError,ValueError):continue
                if not self.items:
                    return {'matched':True,'status':'no_matches','message':'ملاقيتش أفلام في المجلدات المفهرسة ومجلدات الفيديو المتاحة. حدّد مجلد أفلامك في إعدادات الملفات.','cards':[], 'truncated':result.get('truncated',False)}
            if not self.items or self.clock()-self.at>=180:
                return {'matched':True,'status':'expired','message':'نتائج الأفلام انتهت؛ اطلب البحث من جديد.','cards':[]}
            index=0 if fresh else next((number for word,number in _ORDINALS.items() if re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)',value)),0)
            if value in ('غيره','فيلم تاني','اختار غيره','شغل غيره'):index=(self.selected+1)%len(self.items)
            if index>=len(self.items):return {'matched':True,'status':'needs_clarification','message':'الرقم ده مش ضمن الأفلام اللي لقيتها.','cards':self.cards()}
            self.selected=index;chosen=self.items[index]
            play=bool(_PLAY.search(value) or (getattr(policy,'direct_commands',False) and _RECOMMEND.search(value)))
            message='اقتراحي من الموجود عندك: '+chosen['name']+'. الاختيار من الملفات المتاحة حسب النسخة، مش تقييم فني للفيلم.'
            if not play:return {'matched':True,'status':'ok','message':message,'cards':self.cards()}
            path=Path(chosen['_path'])
            try:
                stat=path.stat()
                if path.resolve(strict=True)!=path or (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)!=chosen['_identity']:
                    raise ValueError('changed')
                if sensitive(str(path)) or path.suffix.lower() not in EXTENSIONS:raise ValueError('changed')
            except (OSError,ValueError):
                return {'matched':True,'status':'changed','message':'الفيلم اتحرك أو اتغير بعد البحث؛ مش هفتح ملف مختلف. اطلب البحث تاني.','cards':self.cards()}
            # Re-read permission at action time; discovery cannot grant a launch.
            current=self._policy()
            if not current.enabled:return {'matched':True,'status':'disabled','message':'إذن التحكم اتقفل قبل التشغيل.','cards':self.cards()}
            manager=self._manager();manager.policy=current
            try:outcome=await asyncio.to_thread(manager.launch_direct,'open_file',{'path':str(path)},source=source)
            except (ValueError,RuntimeError,OSError) as exc:
                return {'matched':True,'status':'failed','message':'لقيت الفيلم لكن مشغّل الفيديو لم يؤكد فتحه. راجع مشغّل الفيديو الافتراضي.','cards':self.cards()}
            opened=outcome.get('status')=='opened'
            return {'matched':True,'status':'opened' if opened else outcome.get('status','failed'),
                    'message':message+(' وبعت الفيلم لمشغّل الفيديو الافتراضي.' if opened else ' التشغيل متوقف حسب إعدادات التحكم الحالية.'),
                    'cards':self.cards()}


_SESSIONS:OrderedDict[str,MediaAssistant]=OrderedDict()
def session(conversation_id:str)->MediaAssistant:
    key=str(conversation_id)[:80]
    if key not in _SESSIONS:_SESSIONS[key]=MediaAssistant()
    _SESSIONS.move_to_end(key)
    while len(_SESSIONS)>32:_SESSIONS.popitem(last=False)
    return _SESSIONS[key]
