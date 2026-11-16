"""Ephemeral transcript consistency gate for voice-triggered Windows actions.

NOT voice biometrics: it checks that a recent, explicit spoken request was
transcribed, and that a proposed action appears compatible with that request.
This reduces accidental model/tool triggering but cannot identify a speaker.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import time
import unicodedata

ACTION_WORDS=('افتح','شغل','اعمل','انشئ','اكتب','اضبط','غير','قفل','اقفل','حرك',
              'كبر','صغر','روح','ابحث','دور','start','open','launch','write',
              'create','set','close','switch','search','click','copy','save')
NEGATION_WORDS=('متفتحش','متعملش','ماتفتحش','لا تفتح','لا تشغل',"don't",'do not',
                'hypothetically','افترض','لو قلت','مثلا لو','لو حد قال')
NOISE=('يا','برق','ممكن','بعد','كده','الرجاء','لو','سمحت','عايز','عاوز','please',
       'the','a','on','my','في','على','من','الى','لي','and','to')


def normalize(value:str)->str:
    value=unicodedata.normalize('NFKC',value).casefold()
    value=re.sub(r'[\u064b-\u065fـ]','',value)
    for old,new in [('أ','ا'),('إ','ا'),('آ','ا'),('ى','ي')]:value=value.replace(old,new)
    return re.sub(r'[^\w\s]',' ',value).strip()


def tokens(value:str)->set[str]:
    return {part for part in normalize(value).split() if len(part)>2 and part not in NOISE}


@dataclass
class VoiceCommandGate:
    last_text:str=''
    last_at:float=0.0
    used:bool=False

    def clear(self) -> None:
        self.last_text = ''
        self.last_at = 0.0
        self.used = False

    def record(self,text:str,now:float|None=None)->None:
        # No filesystem storage; only the current live call retains this text.
        if isinstance(text,str) and text.strip():
            self.last_text=text[:420]
            self.last_at=time.monotonic() if now is None else now
            self.used=False

    def check(self,name:str,args:dict,now:float|None=None)->tuple[bool,str]:
        if name in ('computer_task_status','current_work_status'):
            return True,'Status/stop may always be requested'
        # Hardware read-only facts are handled by the existing consent policy.
        if name=='get_pc_system_facts':return True,'Read only'
        now=time.monotonic() if now is None else now
        if not self.last_text or now-self.last_at>12 or self.used:
            return False,'No fresh transcribed speech for this action'
        transcript=normalize(self.last_text)
        if any(normalize(word) in transcript for word in NEGATION_WORDS):
            return False,'Hypothetical or negated request'
        # Align the optional direct Gemini tools with BARQ's colloquial command
        # parser.  Never trust model args or remove the fresh-speech check.
        from voice.intent import command_text, non_executable
        if non_executable(self.last_text):
            return False,'Not an executable spoken instruction'
        command=normalize(command_text(self.last_text))
        if name=='search_device_files':
            if not any(w in transcript for w in ('ملف','ملفات','مجلد','فين','دور','ابحث','شوف','فتش','جهازي','هارد','file','folder','find','search')):
                return False,'No spoken device file search intent'
            request=normalize(str(args.get('query','')))
            if request and not tokens(request).intersection(tokens(self.last_text)):
                return False,'Requested filename does not match speech'
            return True,'Explicit read-only device search'
        if name=='find_local_movies':
            if not (any(word in transcript for word in ('فيلم','افلام','movie','video','فيديو')) and
                any(word in transcript for word in ('رشح','اختار','شوف','ابحث','دور','وريني','find','recommend','list')) and
                any(word in transcript for word in ('جهازي','الجهاز','الكمبيوتر','الهارد','عندي','my pc','my computer','on my'))):
                return False,'No explicit local-media search request'
            return True,'Explicit local read-only media search'
        if name=='stop_computer_task':
            if not any(word in command.split() for word in ('وقف','وقفها','الغ','الغى','الغي','بطل','stop','cancel')):
                return False,'Stop was not requested by recent speech'
        elif name=='continue_current_work':
            if not any(word in command.split() for word in ('كمل','كمله','كملي','كمليه','تابع','تابعها','استكمل','continue','resume','كملها','كمله','متابعة','كمللي')):
                return False,'Continuation was not requested by recent speech'
        elif name in ('start_computer_task','open_on_computer','open_google_search'):

            if not any(normalize(w) in command.split() for w in ACTION_WORDS):
                return False,'No explicit computer action in transcript'
            request=str(args.get('goal') or args.get('request') or args.get('query') or '')
            if not isinstance(request,str) or not request.strip():
                return False,'Missing action'
            requested=tokens(request);uttered=tokens(self.last_text)
            keywords=requested-set(ACTION_WORDS)
            # If there is a target, require at least one significant matching
            # content word. Safer to ask to repeat than act on unrelated audio.
            if keywords and not keywords.intersection(uttered):
                return False,'Model action target differs from spoken request'
        elif name=='control_windows_setting':
            if not any(w in transcript for w in ('الصوت','مستوي','مستوى','سطوع','الاضاءه',
                                                    'volume','brightness','اعدادات','settings')):
                return False,'Setting change is not grounded in transcript'
        else:
            return False,'Unknown action type'
        self.used=True
        return True,'Recent explicit spoken command matched'
