"""User-triggered launcher endpoints. Never accept arbitrary executable paths from clients."""
from __future__ import annotations
from collections import deque
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field
import asyncio,threading,time,yaml
from core.paths import resource
from .resolver import Resolver
from .indexes import Index
from .preferences import load as launcher_settings,save as save_launcher_settings
from .nlu import clean

router=APIRouter(prefix='/v1/launch',tags=['launcher'])
_instance:Resolver|None=None
_rate=deque(maxlen=20)
_rate_lock=threading.Lock()
_voice_lock=asyncio.Lock()
_voice_choices:list[str]=[]
_voice_deadline:float=0.0

def resolver()->Resolver:
    global _instance
    if _instance is None:
        from computer_control.api import load_policy
        _instance=Resolver(Index(),load_policy())
    return _instance

class ResolveRequest(BaseModel):
    text:str=Field(min_length=1,max_length=240)
    source:str=Field(default='text',pattern='^(text|voice|palette)$')
    query_only:bool=False
class ExecuteRequest(BaseModel):
    candidate_id:str=Field(min_length=16,max_length=80)
    approval_token:str|None=None
class LaunchControl(BaseModel):
    enabled:bool=True

@router.post('/resolve')
async def resolve(req:ResolveRequest):
    prefs=launcher_settings()
    if not prefs['enabled']:return {'decision':'blocked','candidates':[], 'spoken_ar':'التشغيل بالأمر معطّل من الإعدادات.','text_ar':'التشغيل بالأمر معطّل.'}
    from .nlu import parse
    parsed=parse('افتح '+req.text if req.query_only else req.text)
    if parsed and parsed.target_kind in ('folder','file'):
        from services.name_search import enable_for_request
        from computer_control.api import load_policy
        enable_for_request(load_policy())
    try:r=await asyncio.wait_for(asyncio.to_thread(resolver().resolve,req.text,req.source,req.query_only),timeout=4)
    except asyncio.TimeoutError:
        return {'decision':'not_found','candidates':[], 'intent':{'target_kind':parsed.target_kind if parsed else None},
                'spoken_ar':'البحث المحلي أخذ وقت أطول من المتوقع؛ لم يتم فتح أي نتيجة.','text_ar':'البحث المحلي لم ينتهِ خلال المهلة. حدّد القرص أو المجلد الأب لتضييق البحث؛ لم يتم فتح نتيجة بالتخمين.'}
    if r is None:return {'decision':'not_command','candidates':[], 'spoken_ar':'','text_ar':''}
    r.candidates=[c for c in r.candidates if prefs.get({'app':'apps','file':'files','folder':'folders','site':'sites'}.get(c['kind'],''),False)]
    if not r.candidates:r.decision='not_found'
    return r.__dict__

def _launch(candidate_id,approval_token=None):
    from computer_control.api import manager
    r=resolver();entry=r.candidate(candidate_id)
    prefs=launcher_settings()
    if not prefs['enabled']:raise HTTPException(403,'التشغيل بالأمر معطّل.')
    if entry is None:raise HTTPException(410,'الاختيار انتهت صلاحيته؛ دوّر تاني.')
    if not prefs.get({'app':'apps','file':'files','folder':'folders','site':'sites'}.get(entry.kind,''),False):
        raise HTTPException(403,'الفئة دي متوقفة من إعدادات المشغّل.')
    # Do not trust cached paths: verify existence and stable canonical target.
    if entry.realpath is not None:
        try:
            actual=str(Path(entry.args.get('path') or entry.args.get('name')).resolve(strict=True))
            if actual!=entry.realpath:raise HTTPException(409,'الملف اتحرك أو اتغير؛ ابحث مرة تانية.')
        except (ValueError,OSError):raise HTTPException(409,'الملف لم يعد موجودًا.')
    try:
        m=manager()
        # Sync shared policy with settings changed in the computer-control UI.
        m.policy=__import__('computer_control.api',fromlist=['load_policy']).load_policy()
        with _rate_lock:
            now=time.monotonic()
            while _rate and now-_rate[0]>60:_rate.popleft()
            if len(_rate)>=6:raise HTTPException(429,'الحد الأقصى 6 عمليات فتح في الدقيقة.')
            outcome=m.launch_direct(entry.tool,entry.args,entry.source,
                                     approved_token=approval_token,approval_id=approval_token)
            if outcome['status']=='opened':
                _rate.append(now)
                if entry.kind in ('file','folder'):
                    from services.personal_assistant import remember
                    remember('last_file',entry.args.get('path',''))
        return {'candidate':{'id':entry.id,'kind':entry.kind,'label':entry.label},
                **outcome,'audit_id':'launcher'}
    except HTTPException:raise
    except (RuntimeError,ValueError,OSError) as exc:raise HTTPException(409,str(exc)[:300])

@router.post('/execute')
def execute(req:ExecuteRequest):
    return _launch(req.candidate_id,req.approval_token)

@router.get('/status')
def status():
    output=resolver().index.status()
    output['supported']=__import__('sys').platform=='win32'
    return output

@router.post('/reindex')
def reindex():
    r=resolver();prefs=launcher_settings()
    if prefs['extra_roots']:
        roots=r.index.default_roots()+[Path(p) for p in prefs['extra_roots']]
        r.index.roots=roots
    return r.index.reindex()

@router.post('/voice')
async def voice(request:Request):
    # Explicit push-to-talk request only. Gemini Live never calls this route.
    if _voice_lock.locked():raise HTTPException(429,'فيه أمر صوتي بيتعالج دلوقتي.')
    async with _voice_lock:
        from voice.gemini import validate_audio, transcribe_audio,VoiceError
        body=await request.body()
        mime=request.headers.get('content-type','')
        prefs=launcher_settings()
        if not prefs['enabled'] or not prefs['voice_enabled']:raise HTTPException(403,'الأوامر الصوتية معطّلة.')
        try:
            validate_audio(body,mime)
            if prefs['stt']=='local':
                transcript=await asyncio.to_thread(_local_transcribe,body,prefs['local_stt_model_path'])
            else:
                transcript=await transcribe_audio(body,mime)
        except VoiceError as exc:raise HTTPException(400,str(exc))
        # Only explicit spoken ordinal choices, never a spoken approval/yes.
        global _voice_choices,_voice_deadline
        ordinal=clean(transcript).strip()
        number={'الاول':0,'اول':0,'رقم 1':0,'واحد':0,
                'التاني':1,'الثاني':1,'رقم 2':1,'اتنين':1,
                'التالت':2,'الثالث':2,'رقم 3':2,'تلاته':2,
                'الرابع':3,'رقم 4':3,'اربعه':3}.get(ordinal)
        if ordinal in ('لا','الغي','الغاء','cancel'):
            _voice_choices=[];return {'transcript':transcript,'decision':'cancelled','text_ar':'تمام، لغيت الاختيار.'}
        if number is not None and time.monotonic()<_voice_deadline and number<len(_voice_choices):
            picked=_voice_choices[number];_voice_choices=[]
            candidate=resolver().candidate(picked)
            if not candidate:return {'transcript':transcript,'decision':'not_found','text_ar':'الاختيار انتهى؛ دوّر تاني.'}
            return {'transcript':transcript,'decision':'selected','candidates':[{'id':picked,'label':candidate.label,'kind':candidate.kind,'risk':candidate.risk}],
                'execution':_launch(picked),'text_ar':'لقيت '+candidate.label}
        # Audio is transient and is not written to disk or persisted in the index.
        result=resolver().resolve(transcript,'voice')
        if not result:return {'transcript':transcript,'decision':'not_command','text_ar':'ده مش أمر فتح؛ تقدر تبعته في الشات.'}
        response={'transcript':transcript,**result.__dict__}
        if result.decision=='choose':
            _voice_choices=[x['id'] for x in result.candidates[:4]]
            _voice_deadline=time.monotonic()+10
        if result.decision=='auto' and result.candidates:
            response['execution']=_launch(result.candidates[0]['id'])
        return response

def local_chat_launch(messages:list[dict]):
    """Never forward a recognized typed launch request (including missing paths) to LLMs."""
    if not messages:return None
    last=messages[-1]
    if last.get('role')!='user' or not isinstance(last.get('content'),str):return None
    # Never execute the opening prefix of a longer project/chat message.
    # The resolver accepts short commands, not truncated task specifications.
    if len(last['content'])>240:return None
    if not launcher_settings()['enabled']:return None
    result=resolver().resolve(last['content'],'text')
    if result is None:return None
    reply=result.text_ar
    if result.decision=='auto' and result.candidates:
        try:
            outcome=_launch(result.candidates[0]['id'])
            reply=('تمام، فتحتلك '+result.candidates[0]['label']+'.') if outcome.get('status')=='opened' else 'التشغيل محتاج موافقة من شاشة برق.'
        except HTTPException as exc:
            reply='التشغيل ماكملش: '+str(exc.detail)[:130]
    elif result.decision in ('choose','ask_approval'):
        reply+=' افتح مشغّل برق السريع علشان تختار وتوافق.'
    return reply


def _local_transcribe(blob:bytes,model_dir:str):
    """Opt-in local Whisper model. Files are ephemeral and securely unlinked."""
    from voice.gemini import VoiceError
    if not model_dir or not Path(model_dir).is_dir():
        raise VoiceError('لازم تثبّت موديل faster-whisper محليًا وتحدد مجلده من الإعدادات أولًا.')
    try:
        from faster_whisper import WhisperModel
    except ImportError:raise VoiceError('ثبّت faster-whisper بنفسك الأول، مفيش تنزيل تلقائي.')
    import io
    model=WhisperModel(model_dir,device='cpu',compute_type='int8',local_files_only=True)
    chunks,_=model.transcribe(io.BytesIO(blob),language='ar',beam_size=3)
    return ' '.join(piece.text.strip() for piece in chunks).strip()

class PreferenceUpdate(BaseModel):
    values:dict
@router.get('/settings')
def settings():return launcher_settings()
@router.put('/settings')
def update_settings(req:PreferenceUpdate):
    try:return save_launcher_settings(req.values)
    except ValueError as exc:raise HTTPException(400,str(exc))


class DenyRequest(BaseModel):
    candidate_id:str=Field(min_length=16,max_length=80)
@router.post('/deny')
def deny(req:DenyRequest):
    entry=resolver().candidate(req.candidate_id)
    if not entry:raise HTTPException(410,'الاختيار انتهت صلاحيته.')
    from computer_control.api import manager
    m=manager()
    m.audit.add('launcher','launch_denied',source=entry.source,tool=entry.tool,decision='denied')
    return {'denied':True}

class AliasRequest(BaseModel):
    alias:str=Field(min_length=2,max_length=100)
    app_name:str=Field(min_length=2,max_length=100)
@router.post('/aliases')
def add_alias(req:AliasRequest):
    """Names only; never accepts a command, absolute path or URL as app target."""
    from .aliases import catalog
    from core.paths import state_file
    import re
    if any(x in req.app_name for x in '/\\:$') or '..' in req.app_name:
        raise HTTPException(400,'اختار اسم برنامج مش مسار أو أمر.')
    names=set(catalog().get('apps',{}))
    names.update(x.get('label','') for x in resolver().app_source())
    target=next((name for name in names if name.casefold()==req.app_name.casefold()),None)
    if not target:raise HTTPException(404,'البرنامج مش موجود ضمن البرامج المتاحة.')
    path=state_file('app_aliases.user.yaml')
    old={}
    if path.exists():
        try:old=yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        except (OSError,yaml.YAMLError):old={}
    aliases=old.setdefault('apps',{}).setdefault(target,[])
    if req.alias not in aliases:aliases.append(req.alias)
    path.write_text(yaml.safe_dump(old,allow_unicode=True,sort_keys=False),encoding='utf-8')
    return {'saved':True,'label':target}

@router.get('/history')
def history():
    from computer_control.audit.journal import Audit
    entries=Audit().recent('launcher',limit=35)
    return {'entries':entries}
