from voice.app_tools import LIVE_APP_TOOLS
from voice.brain_bridge import LIVE_BARQ_TOOLS
"""Regression tests for Gemini Live -> audited Windows computer control integration."""
import asyncio
from types import SimpleNamespace as NS

import pytest
from voice import computer_tools as tools


class FakeTask:
    def __init__(self, goal='افتح المفكرة', status='running'):
        self.id='task-test'
        self.goal=goal
        self.status=status
    def public(self):
        return {'id':self.id,'goal':self.goal,'status':self.status,
                'progress':1,'message':'in progress','pending':None}


class FakeManager:
    def __init__(self):
        self.current=None
        self.started=[]
        self.stopped=0
        self.approvals=0
    def start(self,goal,model):
        self.started.append((goal,model))
        self.current=FakeTask(goal)
        return self.current.public()
    def stop(self):
        self.stopped+=1
        self.current.status='stopped'
        return {'stopped':True}
    def approve(self,*args):
        self.approvals+=1
        raise AssertionError('No voice approval function is allowed')


def test_only_audited_task_level_functions_are_advertised():
    defined={f['name'] for f in tools.LIVE_COMPUTER_TOOLS[0]['function_declarations']}
    assert {'start_computer_task','open_on_computer','computer_task_status','stop_computer_task','get_pc_system_facts','control_windows_setting','open_google_search','current_work_status','continue_current_work','find_local_movies','search_device_files'} <= defined
    assert not {'run_command','approve','click','write_file','delete'} & defined
    assert 'read safe' in next(f['description'] for f in tools.LIVE_COMPUTER_TOOLS[0]['function_declarations'] if f['name']=='get_pc_system_facts')
    assert 'on-screen' in tools.LIVE_CONTROL_INSTRUCTION


@pytest.mark.asyncio
async def test_system_facts_are_read_only_and_require_explicit_consent(monkeypatch):
    from core import windows_facts
    m=FakeManager()
    m.policy=NS(enabled=False)
    monkeypatch.setattr(windows_facts.platform,'system',lambda:'Windows')
    monkeypatch.setattr(windows_facts,'_is_enabled',lambda:True)
    monkeypatch.setattr(windows_facts,'snapshot',lambda:{'ram_gb':16,'ram_available_gb':8})
    disabled=await tools.dispatch_computer_tool('get_pc_system_facts',{'question':'الرام كام'},manager_instance=m)
    assert disabled['status']=='disabled' and not m.started
    m.policy.enabled=True
    allowed=await tools.dispatch_computer_tool('get_pc_system_facts',{'question':'الرام كام'},manager_instance=m)
    assert allowed['status']=='ok' and '16' in allowed['message']
    assert not m.started and m.approvals==0


def test_user_must_opt_in_and_use_windows(monkeypatch):
    monkeypatch.setattr(tools,'sys',NS(platform='win32'))
    assert tools.enabled_on_platform(True)
    assert not tools.enabled_on_platform(False)
    monkeypatch.setattr(tools,'sys',NS(platform='linux'))
    assert not tools.enabled_on_platform(True)


@pytest.mark.asyncio
async def test_start_status_stop_are_delegated_to_policy_manager():
    m=FakeManager()
    a=await tools.dispatch_computer_tool('start_computer_task',{'goal':'افتح المفكرة'},manager_instance=m)
    assert a['status']=='started' and a['task_id']=='task-test'
    assert m.started==[('افتح المفكرة','auto')]
    b=await tools.dispatch_computer_tool('computer_task_status',{},manager_instance=m)
    assert b['status']=='running' and b['progress']==1
    assert 'history' not in b and 'pending' not in b
    c=await tools.dispatch_computer_tool('stop_computer_task',{},manager_instance=m)
    assert c['status']=='stopped' and m.stopped==1
    assert m.approvals==0


@pytest.mark.asyncio
async def test_invalid_and_concurrent_commands_never_start_second_task():
    m=FakeManager()
    for name,arg in [('execute_shell',{'cmd':'whoami'}),('approve',{'accepted':True}),
                     ('start_computer_task',{'goal':''}),('start_computer_task',{'goal':'x'*3001}),
                     ('start_computer_task',{'goal':17}),('open_on_computer',{'request':''}),('start_computer_task','not object')]:
        result=await tools.dispatch_computer_tool(name,arg,manager_instance=m)
        assert result['status']=='denied'
    assert m.started==[]
    await tools.dispatch_computer_tool('start_computer_task',{'goal':'افتح الآلة الحاسبة'},manager_instance=m)
    busy=await tools.dispatch_computer_tool('start_computer_task',{'goal':'افتح المفكرة'},manager_instance=m)
    assert busy['status']=='busy' and len(m.started)==1
    assert m.approvals==0


@pytest.mark.asyncio
async def test_get_status_on_idle_is_not_hallucinated():
    result=await tools.dispatch_computer_tool('computer_task_status',{},manager_instance=FakeManager())
    assert result['status']=='idle'


def test_live_interface_contains_screen_approval_and_real_stop():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    frontend=(root/'frontend/src/components/chat/LiveVoiceDialog.tsx').read_text(encoding='utf-8')
    transport=(root/'frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    live=(root/'voice/live.py').read_text(encoding='utf-8')
    assert 'start_computer_task' in (root/'voice/computer_tools.py').read_text(encoding='utf-8')
    assert "'/v1/computer/approve'" in frontend
    assert 'computerTask.pending' in frontend
    assert "'/v1/computer/stop'" in frontend
    assert 'computerEnabled' in transport and 'computer=' in transport
    assert "session.send_tool_response(function_responses=replies)" in live
    assert 'dispatch_computer_tool(fc.name,arguments,linked_chat_id)' in live


def test_live_websocket_tool_call_is_audited_and_tool_response_sent(monkeypatch):
    """Exercise real FastAPI WS control flow with a synthetic Gemini tool call."""
    import sys
    import types
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from voice import live
    import google
    calls=[]
    sessions=[]
    class FakeSession:
        async def __aenter__(self):
            self.wait=asyncio.Event()
            return self
        async def __aexit__(self,*args):pass
        async def send_client_content(self,**kwargs):pass
        async def send_tool_response(self,**kwargs):
            calls.append(('reply',kwargs['function_responses']))
        async def receive(self):
            # Tool call must follow a fresh transcribed spoken command.
            yield NS(tool_call=None,server_content=NS(input_transcription=NS(text='افتح كروم',finished=True),output_transcription=None,model_turn=None,interrupted=False,turn_complete=False))
            yield NS(tool_call=NS(function_calls=[NS(id='call1',name='ask_barq',args={'request':'افتح تطبيق تاني'})]),server_content=None)
            await self.wait.wait()
    class FakeClient:
        def __init__(self,**kwargs):
            self.aio=NS(live=NS(connect=self.connect),aclose=self.close)
        def connect(self,**kwargs):
            calls.append(('config',kwargs['config']))
            new=FakeSession();sessions.append(new);return new
        async def close(self):pass
    fake=types.ModuleType('google.genai')
    fake.Client=FakeClient
    fake.types=NS(FunctionResponse=lambda **k:NS(**k))
    monkeypatch.setitem(sys.modules,'google.genai',fake)
    monkeypatch.setattr(google,'genai',fake,raising=False)
    monkeypatch.setattr(live,'gemini_key',lambda:'mock-key')
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    monkeypatch.setattr(live,'enabled_on_platform',lambda enabled:bool(enabled))
    from computer_control import api as computer_api
    from computer_control.safety.policy import Policy
    monkeypatch.setattr(computer_api,'load_policy',lambda:Policy(enabled=True))
    async def fake_control(name,args,conversation_id=''):
        calls.append(('dispatch',name,args,conversation_id))
        return {'status':'approval_required','message':'محتاج موافقة','_ui':{'candidate_id':'candidate1','approval_token':'secret-token','label':'Chrome'}}
    from voice.brain_bridge import BARQVoiceBrain
    monkeypatch.setattr(live,'BARQVoiceBrain',lambda:BARQVoiceBrain(dispatcher=fake_control))
    app=FastAPI();app.websocket('/live')(live.handle_live)
    with TestClient(app).websocket_connect('/live?computer=1&conversation_id=chat_1') as ws:
        ready=ws.receive_json();assert ready['type']=='ready' and ready['computer_enabled']
        transcribed=ws.receive_json();assert transcribed['type']=='input_text'
        approval=ws.receive_json();assert approval['type']=='launch_approval' and approval['approval_token']=='secret-token'
        event=ws.receive_json();assert event['type']=='barq_task' and event['status']=='approval_required'
        text=ws.receive_json();assert text['type']=='verified_output_text'
        ws.send_json({'type':'end'})
    assert [c[0] for c in calls]==['config','dispatch','reply']
    from voice.public_tools import LIVE_PUBLIC_TOOLS
    from voice.live import LIVE_REPOSITORY_TOOLS
    assert calls[0][1]['tools']==LIVE_BARQ_TOOLS + LIVE_PUBLIC_TOOLS + LIVE_REPOSITORY_TOOLS + LIVE_APP_TOOLS + tools.LIVE_COMPUTER_TOOLS
    assert calls[1][1:]==('open_on_computer',{'request':'افتح كروم'},'chat_1')
    response=calls[2][1][0]
    assert response.name=='ask_barq' and response.id=='call1' and response.response['status']=='approval_required'
    assert 'secret-token' not in str(response.response) and '_ui' not in response.response


def test_live_conversation_only_has_no_control_tools(monkeypatch):
    import sys,types
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from voice import live
    import google
    captured=[]
    class Session:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def receive(self):
            await asyncio.Event().wait()
            yield None
    class Client:
        def __init__(self,**kwargs):self.aio=NS(live=NS(connect=self.connect),aclose=self.close)
        def connect(self,**kwargs):captured.append(kwargs['config']);return Session()
        async def close(self):pass
    fake=types.ModuleType('google.genai');fake.Client=Client;fake.types=NS()
    monkeypatch.setitem(sys.modules,'google.genai',fake)
    monkeypatch.setattr(google,'genai',fake,raising=False)
    monkeypatch.setattr(live,'gemini_key',lambda:'mock-key')
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    monkeypatch.setattr(live,'enabled_on_platform',lambda enabled:bool(enabled))
    app=FastAPI();app.websocket('/live')(live.handle_live)
    with TestClient(app).websocket_connect('/live?computer=0') as ws:
        assert ws.receive_json()['computer_enabled'] is False
        ws.send_json({'type':'end'})
    from voice.public_tools import LIVE_PUBLIC_TOOLS
    from voice.live import LIVE_REPOSITORY_TOOLS
    assert len(captured)==1 and captured[0]['tools']==LIVE_BARQ_TOOLS + LIVE_PUBLIC_TOOLS + LIVE_REPOSITORY_TOOLS + LIVE_APP_TOOLS
    assert 'open_on_computer' not in str(captured[0]['tools'])
    assert 'start_computer_task' not in str(captured[0]['tools'])
    assert 'prepare_github_repository' in str(captured[0]['tools'])


@pytest.mark.asyncio
async def test_software_opening_uses_existing_launcher_approval_not_raw_exec(monkeypatch):
    import launcher.api as launcher
    monkeypatch.setattr(launcher,'resolver',lambda:NS(resolve=lambda text,source:NS(
        decision='ask_approval',candidates=[{'id':'candidate1','kind':'app','label':'Chrome'}])))
    called=[]
    monkeypatch.setattr(launcher,'_launch',lambda cid:(called.append(cid) or {
        'status':'approval','approval_id':'token1'}))
    result=await tools.dispatch_computer_tool('open_on_computer',{'request':'افتح كروم'},manager_instance=FakeManager())
    assert result['status']=='approval_required'
    assert result['_ui']=={'candidate_id':'candidate1','approval_token':'token1','label':'Chrome'}
    assert called==['candidate1']


@pytest.mark.asyncio
async def test_software_opening_no_ambiguous_launch_without_selection(monkeypatch):
    import launcher.api as launcher
    monkeypatch.setattr(launcher,'resolver',lambda:NS(resolve=lambda text,source:NS(
        decision='choose',candidates=[{'id':'one','kind':'app','label':'Chrome'},
                                      {'id':'two','kind':'app','label':'Chromium'}])))
    def forbidden_launch(*args):raise AssertionError('Must not launch ambiguous app')
    monkeypatch.setattr(launcher,'_launch',forbidden_launch)
    result=await tools.dispatch_computer_tool('open_on_computer',{'request':'افتح كروم'},manager_instance=FakeManager())
    assert result['status']=='choose'
    assert result['candidates']==['Chrome','Chromium']
