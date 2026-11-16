"""Loopback-only, opt-in computer control API. No generic unaudited tool-run endpoint."""
from __future__ import annotations
from fastapi import APIRouter,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel,Field
from pathlib import Path
import asyncio,json,sys
from computer_control.adapters.desktop import default_adapter
from computer_control.safety.policy import Policy,Mode
from computer_control.executor.manager import Manager
from core.paths import state_file,resource

router=APIRouter(prefix='/v1/computer',tags=['computer-control'])
_manager:Manager|None=None

def manager()->Manager:
    global _manager
    if _manager is None:
        if sys.platform!='win32':raise HTTPException(501,'Desktop control requires Windows 10/11 interactive session')
        from api import engine  # preserve the existing BARQ router
        _manager=Manager(default_adapter(),engine,load_policy())
    return _manager

def load_policy()->Policy:
    import yaml
    doc={}
    path=state_file('computer_control_settings.json')
    if path.exists():
        try:doc=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
    else:
        try:doc=yaml.safe_load(resource('config','computer_control.yaml').read_text(encoding='utf-8')) or {}
        except (ValueError,OSError):pass
    # Existing installations also require an explicit consent decision.
    doc.setdefault('enabled', False)
    doc.setdefault('direct_commands', True)
    if type(doc['direct_commands']) is not bool:doc['direct_commands']=False
    values={k:v for k,v in doc.items() if k in Policy.__dataclass_fields__}
    try:
        if 'mode' in values:values['mode']=Mode(values['mode'])
        p=Policy(**values)
        p.allowed_folders=[str(Path(path).expanduser().resolve()) for path in p.allowed_folders]
        return p
    except (ValueError,TypeError):return Policy()

class Start(BaseModel):
    conversation_id:str=Field(default='',max_length=80)
    goal:str=Field(min_length=2,max_length=3000)
    model:str='auto'
class Settings(BaseModel):
    enabled:bool=False
    direct_commands:bool=True
    mode:Mode=Mode.SMART
    local_only_vision:bool=True
    allowed_folders:list[str]=Field(max_length=10)
    max_steps:int=Field(default=40,ge=1,le=100)
    max_seconds:int=Field(default=600,ge=10,le=3600)
    max_failures:int=Field(default=3,ge=1,le=10)
    max_files:int=Field(default=20,ge=1,le=100)
    actions_per_second:float=Field(default=4,ge=.2,le=10)
class ContinueTask(BaseModel):
    task_id:str=Field(min_length=16,max_length=80)
    confirmed:bool=False

class ToolPreview(BaseModel):
    tool:str
    args:dict=Field(default_factory=dict)
class Approve(BaseModel):
    id:str
    accepted:bool
    updated_args:dict|None=None
    remember_exact:bool=False

class GrantRequest(BaseModel):
    root:str=Field(min_length=3,max_length=1024)
    scopes:list[str]=Field(min_length=1,max_length=8)
    label:str=Field(default='',max_length=100)

@router.get('/execution/doctor')
def execution_doctor():
    from execution.doctor import report
    return report()

@router.get('/execution/grants')
def execution_grants():
    from execution.grants import GrantStore
    from dataclasses import asdict
    return {'grants':[asdict(item) for item in GrantStore().all()]}

@router.post('/execution/grants')
def execution_grant(req:GrantRequest):
    if not load_policy().enabled:
        raise HTTPException(403,'Enable Computer Control before granting a project')
    from execution.grants import GrantStore
    from dataclasses import asdict
    try:return asdict(GrantStore().grant(req.root,req.scopes,req.label))
    except (OSError,ValueError) as exc:raise HTTPException(400,str(exc))

@router.delete('/execution/grants/{grant_id}')
def execution_revoke(grant_id:str):
    from execution.grants import GrantStore
    if len(grant_id)!=32 or not all(c in '0123456789abcdef' for c in grant_id):
        raise HTTPException(400,'Invalid project grant ID')
    return {'revoked':GrantStore().revoke(grant_id)}

@router.post('/execution/revoke-all')
def execution_revoke_all():
    from execution.grants import GrantStore
    GrantStore().revoke_all()
    return {'revoked':True}

@router.post('/execution/pick-folder')
def execution_pick_folder():
    if sys.platform!='win32':raise HTTPException(501,'Windows interactive desktop required')
    if not load_policy().enabled:raise HTTPException(403,'Enable Computer Control first')
    try:
        from tkinter import Tk, filedialog
        root=Tk();root.withdraw();root.attributes('-topmost',True)
        try:selected=filedialog.askdirectory(parent=root,title='BARQ — اختر مجلد المشروع')
        finally:root.destroy()
        if not selected:return {'cancelled':True,'path':None}
        from execution.grants import GrantStore
        GrantStore.validate_root(selected)
        return {'cancelled':False,'path':selected,'granted':False}
    except (OSError,RuntimeError,ValueError) as exc:
        raise HTTPException(400,str(exc))

@router.post('/execution/preview-react')
def execution_preview_react():
    return {'kind':'react-vite','steps':['grant','create','npm install --ignore-scripts',
            'npm run build','HTTP readiness'], 'executed':False,
            'requires_explicit_project_grant':True}

@router.get('/windows-mcp')
def windows_mcp_status():
    from mcp.windows_client import installation_status
    return installation_status()

@router.get('/standard-user-folders')
def standard_user_folders():
    """Display opt-in choices for ordinary writable folders on this profile.

    Returning folders does not grant access. The existing /settings write is
    an explicit user UI action, persisted with all normal safety checks.
    """
    from computer_control.safety.policy import sensitive
    home=Path.home()
    paths=[home/'AgentWorkspace', home/'Desktop', home/'Documents', home/'Downloads']
    folders=[]
    for path in paths:
        if path.is_dir() and not sensitive(str(path)):
            folders.append(str(path.resolve()))
    return {'folders':folders, 'granted':False}

@router.get('/status')
def status():
    if sys.platform!='win32' and _manager is None:
        return {'supported':False,'status':'not_supported','reason':'Windows desktop required','policy':load_policy().mode.value}
    m=manager()
    from computer_control.health import snapshot
    from execution.service import ExecutionService
    return {'supported':True,'task':ExecutionService(m).current_task(),'settings':m.settings(),
            'health':snapshot(), 'recovered_count':m.recovered_count}
@router.put('/settings')
def update_settings(req:Settings):
    m=manager()
    try:
        state=m.set_policy(**req.model_dump())
        persist={k:v for k,v in state.items() if k in Settings.model_fields}
        dest=state_file('computer_control_settings.json')
        dest.write_text(json.dumps(persist,indent=2,ensure_ascii=False),encoding='utf-8')
        return state
    except (RuntimeError,ValueError) as exc:raise HTTPException(400,str(exc))
@router.post('/preview')
def preview(req:ToolPreview):
    from computer_control.tools.schema import validate
    try:validate(req.tool,req.args)
    except ValueError as exc:raise HTTPException(400,str(exc))
    risk,decision,reason=manager().policy.evaluate(req.tool,req.args)
    return {'tool':req.tool,'risk':risk.value,'decision':decision.value,'reason':reason,'executed':False}
@router.post('/start')
async def start(req:Start):
    try:
        from execution.service import ExecutionService
        started=ExecutionService(manager()).submit(req.goal,source='chat',model=req.model)
        if started.get('id'):
            try:
                from api import brain
                started['brain_task_id']=brain.track_computer(req.goal,req.model,req.conversation_id,started)
            except Exception:
                # Intake tracking must not report an already started OS task as rejected.
                pass
        return started
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc))
@router.get('/checkpoints')
def checkpoints(limit:int=12):
    m=manager()
    return {'tasks':m.task_history(min(30,max(1,limit))),
            'interrupted_on_startup':m.recovered_count,
            'note':'Saved actions never resume automatically; explicit confirmation starts a fresh observation.'}

@router.get('/tasks/{task_id}')
def task_by_id(task_id:str):
    from execution.service import ExecutionService
    task=ExecutionService(manager()).task_by_id(task_id)
    if task is None:
        raise HTTPException(404,'Computer task not found')
    return {**task,'pending':task.get('pending')}

@router.post('/continue')
async def continue_task(req:ContinueTask):
    try:
        return manager().continue_interrupted(req.task_id,confirmed=req.confirmed)
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(409,str(exc))

@router.post('/stop')
async def stop():
    from execution.react_mission import mission
    running=mission().public()
    if running and running['status'] in ('planning','running'):
        return mission().stop()
    return manager().stop()
@router.post('/approve')
async def approve(req:Approve):
    try:return manager().approve(req.id,req.accepted,req.updated_args,req.remember_exact)
    except ValueError as exc:raise HTTPException(400,str(exc))
@router.post('/undo')
def undo():
    try:return manager().undo_last()
    except RuntimeError as exc:raise HTTPException(409,str(exc))
@router.post('/undo-all')
def undo_all():
    try:return manager().undo_all()
    except RuntimeError as exc:raise HTTPException(409,str(exc))
@router.get('/audit')
def audit(limit:int=50):
    m=manager()
    return {'entries':m.audit.recent(m.current.id,min(200,max(1,limit))) if m.current else []}
@router.get('/screenshot')
def screenshot():
    m=manager()
    if not m.current or m.current.status not in ('running','approval','planning'):
        raise HTTPException(409,'No active computer control task')
    frame=m.adapter.perceive()
    data=frame.screenshot_png
    if not data:raise HTTPException(503,'Screenshot unavailable; check screen capture permission')
    # Mark a known UI tree element or explicit click coordinate. This preview is
    # visible only to the authenticated local UI and is never sent to a provider.
    pending=m.current.pending
    if pending and pending.tool in ('click','double_click','hover','drag','invoke_ui','set_ui_text') and frame.screenshot_bounds:
        try:
            import io
            from PIL import Image,ImageDraw
            image=Image.open(io.BytesIO(data)).convert('RGB')
            x0,y0,w,h=frame.screenshot_bounds
            target=next((e for e in frame.elements if e.get('id')==pending.args.get('element_id')),None)
            if target:rect=target['rect']
            elif 'x' in pending.args and 'y' in pending.args:
                x,y=int(pending.args['x']),int(pending.args['y']);rect=[x-12,y-12,x+12,y+12]
            else:rect=None
            if rect:
                scale_x=image.width/w;scale_y=image.height/h
                box=[(rect[0]-x0)*scale_x,(rect[1]-y0)*scale_y,(rect[2]-x0)*scale_x,(rect[3]-y0)*scale_y]
                ImageDraw.Draw(image).rectangle(box,outline='#E52235',width=4)
                output=io.BytesIO();image.save(output,format='PNG');data=output.getvalue()
        except Exception:pass
    return Response(data,media_type='image/png',headers={'Cache-Control':'no-store'})
@router.websocket('/events')
async def events(ws:WebSocket):
    host=ws.headers.get('host','').split(':',1)[0].lower()
    origin=ws.headers.get('origin')
    if host not in ('localhost','127.0.0.1','[::1]','testserver') or (origin and not origin.endswith('://'+ws.headers.get('host',''))):
        await ws.close(code=1008);return
    await ws.accept()
    try:
        while True:
            m=manager()
            from execution.service import ExecutionService
            await ws.send_json({'task':ExecutionService(m).current_task()})
            await asyncio.sleep(.8)
    except (WebSocketDisconnect,RuntimeError):return


@router.post('/work-area')
def direct_work_area():
    policy=load_policy()
    if not policy.enabled or not policy.direct_commands or policy.mode==Mode.OBSERVE:
        raise HTTPException(403,'التنفيذ المباشر يحتاج تفعيل التحكم في الكمبيوتر.')
    from computer_control.safety.policy import sensitive
    root=Path.home()/'BARQ Projects'
    if root.is_symlink() or sensitive(str(root)):
        raise HTTPException(409,'مجلد مشاريع برق غير متاح.')
    root.mkdir(parents=True,exist_ok=True)
    return {'path':str(root.resolve()),'managed':True}


@router.get('/agent-tools')
def agent_tools():
    from computer_control.tools.screen import runtime_report
    return runtime_report()

@router.post('/read-screen')
async def read_current_screen():
    import asyncio
    m=manager();m.policy=load_policy()
    if not m.policy.enabled:raise HTTPException(403,'فعّل إذن التحكم في الكمبيوتر لقراءة الشاشة.')
    from computer_control.safety.policy import Decision
    if m.policy.evaluate('read_screen',{})[1]!=Decision.ALLOW:raise HTTPException(403,'قراءة الشاشة متوقفة بإعداداتك الحالية.')
    from computer_control.tools.screen import read_screen
    return await asyncio.to_thread(read_screen,m.adapter)


class CompanionCommand(BaseModel):
    text:str=Field(min_length=1,max_length=500)

@router.post('/companion-command')
async def companion_command(body:CompanionCommand):
    from services.desktop_companion import command
    return await command(body.text,source='chat')
