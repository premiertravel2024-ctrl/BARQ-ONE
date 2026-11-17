from voice.app_tools import LIVE_APP_TOOLS
from voice.brain_bridge import LIVE_BARQ_TOOLS
"""Hands-free Gemini Live may use approved desktop tools, never by default."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace as NS
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def run_call(monkeypatch, *, voice_opt_in: bool, desktop_policy: bool):
    from voice import live
    from computer_control import api as pc_api
    from computer_control.safety.policy import Policy
    monkeypatch.setattr(live, 'gemini_key', lambda: 'fake-key')
    monkeypatch.setattr(live, 'enabled_on_platform', lambda flag: bool(flag))
    monkeypatch.delenv('LOCAL_ONLY', raising=False)
    monkeypatch.setattr(pc_api, 'load_policy', lambda: Policy(enabled=desktop_policy))
    calls=[]
    class Session:
        def __init__(self):self.stop=asyncio.Event()
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def send_client_content(self, **kw):pass
        async def send_realtime_input(self, **kw):pass
        async def send_tool_response(self, **kw):calls.append(('result',kw['function_responses']))
        async def receive(self):
            if desktop_policy and voice_opt_in:
                # The voice execution gate must see a REAL transcript before any
                # computer action. Previously this test skipped the transcript.
                yield NS(tool_call=None,server_content=NS(interrupted=False,
                    input_transcription=NS(text='يا برق افتح المفكرة'),
                    output_transcription=None,model_turn=None,turn_complete=False))
                yield NS(tool_call=NS(function_calls=[NS(id='call_7',name='start_computer_task',args={'goal':'افتح المفكرة'})]),server_content=None)
            await self.stop.wait()
    config=[]
    def connect(**kw):
        config.append(kw['config']);return Session()
    class FakeClient:
        def __init__(self,**kw):self.aio=NS(live=NS(connect=connect),aclose=self.close)
        async def close(self):pass
    genai=ModuleType('google.genai');genai.Client=FakeClient
    genai.types=NS(FunctionResponse=lambda **args:NS(**args))
    # The test is deliberately independent of google-genai being installed.
    google=sys.modules.get('google') or ModuleType('google')
    monkeypatch.setitem(sys.modules,'google',google)
    monkeypatch.setitem(sys.modules,'google.genai',genai)
    monkeypatch.setattr(google,'genai',genai,raising=False)
    async def fake_dispatch(name,args,conv):
        calls.append(('dispatch',name,args,conv))
        return {'status':'approval_required','message':'يتطلب موافقة الشاشة',
                '_ui':{'candidate_id':'local-candidate','approval_token':'not-for-cloud','label':'Notepad'}}
    monkeypatch.setattr('voice.computer_tools.dispatch_computer_tool',fake_dispatch)

    async def silent_speech(*args):
        return b'', 'audio/wav'

    monkeypatch.setattr('voice.gemini.synthesize_speech',silent_speech)
    app=FastAPI();app.websocket('/live')(live.handle_live)
    with TestClient(app).websocket_connect('/live?mode=open&computer='+('1' if voice_opt_in else '0')+'&conversation_id=abc_123') as ws:
        event=ws.receive_json()
        assert event['type']=='ready'
        allowed=voice_opt_in and desktop_policy
        assert event['computer_enabled'] is allowed
        if allowed:
            heard=ws.receive_json();assert heard['type']=='input_text'
            assert 'المفكرة' in heard['text']
            approve=ws.receive_json();assert approve['type']=='launch_approval'
            assert approve['approval_token']=='not-for-cloud'
            message=ws.receive_json();assert message['type']=='barq_task'
            assert message['status']=='approval_required'
            assert ws.receive_json()['type']=='verified_output_text'
        ws.send_json({'type':'end'})
    assert len(config)==1
    from voice.public_tools import LIVE_PUBLIC_TOOLS
    from voice.computer_tools import LIVE_COMPUTER_TOOLS
    from voice.live import LIVE_REPOSITORY_TOOLS
    # Repository review is a read-only UI handoff, NOT a desktop permission.
    assert config[0]['tools']==LIVE_BARQ_TOOLS + LIVE_PUBLIC_TOOLS + LIVE_REPOSITORY_TOOLS + LIVE_APP_TOOLS + (LIVE_COMPUTER_TOOLS if allowed else [])
    assert 'prepare_github_repository' in str(config[0]['tools'])
    assert ('start_computer_task' in str(config[0]['tools'])) is allowed
    if voice_opt_in and desktop_policy:
        assert [c[0] for c in calls]==['dispatch','result']
        assert calls[0][1:] == ('open_on_computer',{'request':'يا برق افتح المفكرة'},'abc_123')
        fn=calls[1][1][0]
        assert fn.name=='start_computer_task' and fn.id=='call_7'
        assert 'not-for-cloud' not in str(fn.response)
    else:assert not calls


@pytest.mark.parametrize(('voice_opt_in','desktop_policy'),[(False,False),(False,True),(True,False),(True,True)])
def test_open_conversation_computer_access_requires_two_independent_permissions(monkeypatch,voice_opt_in,desktop_policy):
    run_call(monkeypatch,voice_opt_in=voice_opt_in,desktop_policy=desktop_policy)


def test_handsfree_ui_displays_real_task_status_and_approval_buttons():
    root=Path(__file__).resolve().parents[1]
    settings=(root/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    overlay=(root/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text(encoding='utf-8')
    desktop_status=(root/'frontend/src/components/workspace/ComputerControlStatus.tsx').read_text(encoding='utf-8')
    app=(root/'frontend/src/App.tsx').read_text(encoding='utf-8')
    live=(root/'voice/live.py').read_text(encoding='utf-8')
    assert 'allowComputerInConversation' in settings
    assert 'pcPolicyEnabled' in settings
    assert "computerEnabled:allowComputerInConversation&&pcPolicyEnabled" in settings
    # Hands-free must share the selected chat with typed messages and desktop tasks.
    # Requiring [] here was an obsolete contract: it would re-introduce the bug
    # where the spoken assistant cannot read links sent to the same chat.
    assert 'linkedChat.current=state.activeId' in overlay
    assert 'const history=(state.chats.find(c=>c.id===linkedChat.current)?.messages||[])' in overlay
    assert "await voice.start(state.voiceId,history,allowComputer,linkedChat.current||'',false,true)" in overlay
    assert 'useApp.subscribe(sync)' in overlay
    assert 'live.current?.sendChatContext(' in overlay
    assert 'live.current?.sendWorkState(' in overlay
    assert "void voice.start(state.voiceId,[]," not in overlay
    assert "'/v1/computer/approve'" in desktop_status
    # The user removed the old floating voice window. Its independent safety
    # controls must survive in the chat shell and explicit approval modals.
    assert '<HandsFreeVoice/>' in app
    assert '<ComputerControlStatus/>' in app
    assert 'No always-visible voice HUD' in overlay
    assert "'/v1/computer/status'" in overlay
    assert 'current.task' in overlay
    assert "'/v1/computer/approve'" in desktop_status
    assert "'/v1/launch/execute'" in overlay
    assert '/v1/computer/screenshot?approval=' in desktop_status
    assert 'setComputerReady(!!message.computer_enabled)' in overlay
    assert 'onClick={()=>void decide(false)}' in desktop_status
    assert 'onClick={()=>void decide(true)}' in desktop_status
    # The kill switch is now inside the active chat task card, not a
    # floating overlay; the independent global controller retains approvals.
    inline_chat = (root / 'frontend/src/components/chat/Message.tsx').read_text(encoding='utf-8')
    assert "'/v1/computer/stop'" in inline_chat
    assert "method:'POST'" in inline_chat
    assert "message.agentTask.status==='running'" in inline_chat
    assert 'onClick={()=>void stopComputerTask()}' in inline_chat
    assert 'barq-execution-panel' not in desktop_status
    assert 'computer_enabled=enabled_on_platform(' in live
    assert "computer_enabled=bool(load_policy().enabled)" in live
    assert 'await dispatch_computer_tool(fc.name,arguments,linked_chat_id)' in live
