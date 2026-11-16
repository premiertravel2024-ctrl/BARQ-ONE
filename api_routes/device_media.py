"""Local-only, consent-gated, read-only media search."""
from fastapi import APIRouter,HTTPException,Query
from computer_control.api import load_policy
from services.local_media import discover_movies

router=APIRouter(prefix='/v1/device',tags=['local-device-media'])

@router.get('/movies')
def movies(query:str=Query(default='',max_length=120)):
    policy=load_policy()
    if not policy.enabled:
        raise HTTPException(403,'فعّل إذن الكمبيوتر من إعدادات برق للبحث في ملفات الفيديو المحلية.')
    return discover_movies(policy.allowed_folders,query=query)

from pydantic import BaseModel,Field
from services import device_index

class IndexSettings(BaseModel):
    enabled:bool
    all_local_drives:bool=False
    content_enabled:bool=False

@router.get('/index/status')
def index_status():
    return device_index.status()

@router.put('/index/settings')
def index_settings(payload:IndexSettings):
    if not load_policy().enabled and payload.enabled:
        raise HTTPException(403,'فعّل التفاعل مع الكمبيوتر قبل فهرسة ملفاته.')
    return device_index.configure(enabled=payload.enabled,all_local_drives=payload.all_local_drives,content_enabled=payload.content_enabled)

@router.post('/index/refresh')
def index_refresh():
    policy=load_policy()
    if not policy.enabled:raise HTTPException(403,'إذن الكمبيوتر غير مفعّل.')
    return device_index.refresh(policy.allowed_folders)

@router.get('/index/content-status')
def content_status():
    from services import content_index
    return content_index.status()

@router.post('/index/content-refresh')
def content_refresh():
    from services import content_index
    policy=load_policy()
    if not policy.enabled:raise HTTPException(403,'إذن الكمبيوتر غير مفعّل.')
    return content_index.refresh(policy.allowed_folders)

@router.get('/content-search')
def search_content(query:str=Query(min_length=2,max_length=150)):
    from services import content_index
    policy=load_policy()
    if not policy.enabled:raise HTTPException(403,'إذن الكمبيوتر غير مفعّل.')
    return content_index.search(query,allowed_folders=policy.allowed_folders)

@router.get('/search')
def device_search(query:str=Query(min_length=2,max_length=150),extension:str=Query(default='',max_length=12)):
    policy=load_policy()
    if not policy.enabled:raise HTTPException(403,'إذن الكمبيوتر غير مفعّل.')
    return device_index.search(query,extension=extension,allowed_folders=policy.allowed_folders)

class SearchInstallConsent(BaseModel):
    approved:bool=False

@router.post('/index/install-everything')
def install_official_search_tool(payload:SearchInstallConsent):
    if not load_policy().enabled:
        raise HTTPException(403,'فعّل تحكم الكمبيوتر أولًا.')
    if not device_index.settings().get('enabled'):
        raise HTTPException(403,'فعّل فهرسة الملفات أولًا.')
    return device_index.request_official_search_install(approved=payload.approved)

@router.get('/index/install-status')
def file_search_install_status():
    return device_index.install_status()


class MediaCommand(BaseModel):
    text:str=Field(min_length=1,max_length=600)
    conversation_id:str=Field(default='',max_length=80)

@router.post('/media-command')
async def media_command(payload:MediaCommand):
    from services.media_assistant import session
    return await session(payload.conversation_id).command(payload.text,source='text')


@router.post('/name-command')
async def name_command(payload:MediaCommand):
    import asyncio
    from services.name_search import search_request
    try:return await asyncio.wait_for(asyncio.to_thread(search_request,payload.text),timeout=4)
    except asyncio.TimeoutError:return {'matched':True,'status':'timeout','message':'بحث الأسماء أخذ وقت أطول من المهلة؛ حدّد القرص لتضييق البحث.'}
