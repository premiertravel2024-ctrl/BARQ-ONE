"""Bounded deterministic triage; semantic and tiny-model fallback are opt-in."""
from __future__ import annotations
import re,json
from pathlib import Path
from difflib import SequenceMatcher
from .contracts import Request,TaskProfile

AR = re.compile(r'[\u0600-\u06ff]')
EN = re.compile(r'[a-zA-Z]')
SECRET = re.compile(
    r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----'
    r'|\b(?:sk-[A-Za-z0-9_-]{18,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{35})'
    r'|(?:api[_-]?key|password|token|secret)["\']?\s*[:=]\s*["\']?[^\s,;]{8,}'
    r'|(?:مفتاح\s+(?:الـ?\s*)?API|كلمة\s+(?:المرور|السر)|رمز\s+الوصول)\s*[:=]\s*[^\s,;]{8,}'
    r'|\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{8,}',
    re.IGNORECASE,
)
PII = re.compile(r'(?i)(?:[\w.+-]+@[\w.-]+\.[a-z]{2,}|\+?\d[\d ()-]{9,}\d)')
TIME_SENSITIVE=re.compile(r'(?i)\b(?:today|latest|now|current|weather|news|stock price)\b|النهارد[هة]|حاليا|دلوقتي|الطقس|آخر الأخبار|سعر\s+(?:العملات|السهم)')
PATTERNS=[
 ('translation',r'ترجم|ترجمة|translate|translation'),
 ('debugging',r'خطأ|ايرور|error|traceback|bug|debug|exception|مش شغال|بيهنج|صلح الكود'),
 ('coding',r'(?s)```|\b(?:def |class |import |npm |pip |typescript|python|react|javascript|git commit)\b|برمج|بايثون|كود|اكتب\s+كود|مشروع\s+برمج'),
 ('summarization',r'لخص|تلخيص|اختصر|summari[sz]e|summary|brief this'),
 ('extraction',r'استخرج|استخراج|اطلع\s+البيانات|extract|parse the|استخل[صا]'),
 ('tool',r'افتح\s+(?:الكروم|برنامج|ملف|متصفح)|نفذ|شغل\s+(?:الأداة|البرنامج)|execute|run the|open\s+(?:chrome|browser)|احذف\s+(?:الملف|الفولدر)|تحكم\s+في\s+الكمبيوتر'),
 ('writing',r'اكتب\s+(?:رسالة|مقال|إيميل|بريد)|صياغة\s+بوست|draft|write an? (?:email|post|article)|write a social post'),
 ('reasoning',r'احسب|برهن|اثبت|رياضيات|calculate|solve|integral|equation|معادل[هة]'),
 ('qa',r'\b(?:what|why|how|when|where|who)\b|ازاي|إزاي|ليه|ايه|إيه|ما\s+هو|ماذا\s+يعني'),
]
class Triage:
    def __init__(self, examples=None, min_confidence=.78):
        self.examples=Path(examples) if examples else Path(__file__).resolve().parents[1]/'examples'/'triage.jsonl'
        self.min_confidence=min_confidence
    def classify(self,request:Request)->TaskProfile:
        contents=[m.get('content','') for m in request.messages if m.get('role')=='user']
        text=contents[-1] if contents else ''
        text=text if isinstance(text,str) else str(text)
        all_text=' '.join(str(m.get('content','')) for m in request.messages[-6:])
        lang='ar' if AR.search(text) else 'en'
        if AR.search(text) and EN.search(text) and len(EN.findall(text))>len(AR.findall(text))*.5:lang='mixed'
        kind='chat';confidence=.55;layer='rules'
        if request.attachments:
            image_present=any(str(a.get('type','')).startswith('image/') for a in request.attachments)
            if image_present:kind='vision';confidence=.98
        if isinstance(contents[-1],list) if contents else False:
            if any(isinstance(part,dict) and (part.get('type')=='image_url' or part.get('type')=='input_image') for part in contents[-1]):kind='vision';confidence=.99
        if kind!='vision' and re.search(r'(?i)(?:حلل|اشرح|صف|اقرأ|فسر|image recognition|describe|read|what is in|إيه اللي في)\s+(?:.*?\s+)?(?:الصورة|صورة|لقطة الشاشة|image|photo|screenshot|الرسمة)',text):
            kind='vision';confidence=.92
        if kind!='vision' and re.search(r'(?i)عامل ايه|إزيك|يا برق يا صاحبي|good morning|hello friend',text):
            kind='chat';confidence=.94
        if confidence<.78 and kind!='vision':
            for label,pattern in PATTERNS:
                if re.search(pattern,text,re.I):kind=label;confidence=.88;break
        if kind in ('chat','qa','summarization') and re.search(r'(?i)\bpdf\b|\.pdf\b|مستند\s+طويل|ملف\s+طويل|وثيقة\s+طويلة|long document|\b\d+\s+pages\b|pdf report',text):
            kind='long_document';confidence=.88
        if confidence<self.min_confidence and self.examples.is_file():
            matches=[]
            try:
                for line in self.examples.read_text(encoding='utf-8').splitlines()[:1500]:
                    item=json.loads(line)
                    similarity=SequenceMatcher(None,text[:350].casefold(),str(item.get('text',''))[:350].casefold()).ratio()
                    if item.get('task_type') in TaskProfile.model_fields['task_type'].annotation.__args__:matches.append((similarity,item['task_type']))
                if matches:
                    similar,label=max(matches)
                    if similar>=.87:kind=label;confidence=similar;layer='local_examples_similarity'
            except (OSError,ValueError,KeyError):pass
        length=len(all_text)
        hard= length>22000 or (kind in ('tool','long_document') and length>1200) or (kind in ('coding','debugging') and length>6500)
        medium=length>900 or kind in ('coding','debugging','reasoning','vision','tool','long_document')
        difficulty='hard' if hard else 'medium' if medium else 'easy'
        modality='image' if kind=='vision' else 'file' if request.attachments else 'text'
        return TaskProfile(task_type=kind,domain='software' if kind in ('coding','debugging') else 'general',difficulty=difficulty,language=lang,
            needs_long_context=length>22000 or kind=='long_document',needs_tools=kind=='tool',needs_json=bool(re.search(r'\bJSON\b|صيغة\s+json',text,re.I)),
            modality=modality,latency_sensitivity=.95 if request.mode=='fast' else .45,
            risk='high' if kind=='tool' else 'low',confidence=confidence,layer=layer,
            token_estimate=max(1,(len(all_text)+3)//4))
    @staticmethod
    def privacy_required(request:Request)->bool:
        user_text=' '.join(str(m.get('content','')) for m in request.messages if m.get('role')=='user')
        return bool(SECRET.search(user_text) or PII.search(user_text))
    @staticmethod
    def cacheable(request:Request)->bool:
        txt=' '.join(str(m.get('content','')) for m in request.messages if m.get('role')=='user')
        return request.privacy=='normal' and not request.attachments and not SECRET.search(txt) and not PII.search(txt) and not TIME_SENSITIVE.search(txt) and not request.conversation_id and len(request.messages)<=2
