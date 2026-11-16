"""Regression for video: GitHub URL pasted while hands-free Live remains open."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace as NS
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from voice.repository_context import last_user_repository, prepare_spoken_repository
from voice.live import recent_direct_user_messages, LIVE_REPOSITORY_TOOLS

URL='https://github.com/LibreHardwareMonitor/LibreHardwareMonitor'
TRACKED=URL+'?utm_source=chatgpt.com'


def test_video_tracking_link_and_direct_user_scope():
    assert last_user_repository([{'role':'user','content':TRACKED}]) == URL
    assert last_user_repository([{'role':'assistant','content':TRACKED}]) is None
    assert last_user_repository([{'role':'tool','content':TRACKED}]) is None
    assert prepare_spoken_repository('ثبت الريبو ده',1,URL,now=2)['status']=='preview_ready'


def test_context_read_only_and_no_assistant_leak():
    messages=[{'role':'assistant','content':'private message'},
              {'role':'user','content':'بعتلك لينك المستودع'},
              {'role':'user','content':TRACKED}]
    assert recent_direct_user_messages(messages)==['بعتلك لينك المستودع',TRACKED]
    assert 'read_current_chat_context' in str(LIVE_REPOSITORY_TOOLS)


def test_live_chat_context_can_change_while_socket_is_open(monkeypatch):
    from voice import live
    monkeypatch.setattr(live,'gemini_key',lambda:'fake-test-key')
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    class Session:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def send_client_content(self,**kwargs):pass
        async def send_realtime_input(self,**kwargs):pass
        async def receive(self):
            await asyncio.Event().wait()
            if False:yield None
    session=Session()
    google=ModuleType('google');genai=ModuleType('google.genai')
    genai.types=NS(Blob=lambda **kw:kw,FunctionResponse=lambda **kw:kw)
    genai.Client=lambda **kw:NS(aio=NS(live=NS(connect=lambda **kw:session),aclose=lambda:asyncio.sleep(0)))
    google.genai=genai
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules,'google',google);mp.setitem(sys.modules,'google.genai',genai)
        app=FastAPI();app.websocket('/live')(live.handle_live)
        with TestClient(app).websocket_connect('/live?mode=open') as ws:
            assert ws.receive_json()['type']=='ready'
            ws.send_json({'type':'context','messages':[]})
            # Link arrives AFTER the session's first context snapshot.
            ws.send_json({'type':'chat_context','messages':[
                {'role':'assistant','content':'https://github.com/unsafe/injected'},
                {'role':'user','content':TRACKED}]})
            event=ws.receive_json()
            assert event=={'type':'chat_context_synced','url':URL,'chat_id':''}
            # Remove typed link. Old links must not be reused across edits.
            ws.send_json({'type':'chat_context','messages':[{'role':'assistant','content':TRACKED}]})
            assert ws.receive_json()=={'type':'chat_context_synced','url':None,'chat_id':''}
            # Switching to a newly selected chat must update the ACTIVE
            # voice session; it must not stay attached to the old chat.
            ws.send_json({'type':'chat_context','chat_id':'new_chat_123',
                          'messages':[{'role':'user','content':TRACKED}]})
            assert ws.receive_json()=={'type':'chat_context_synced','url':URL,'chat_id':'new_chat_123'}
            # An invalid chat ID is ignored rather than used as a path/token.
            ws.send_json({'type':'chat_context','chat_id':'../../private',
                          'messages':[{'role':'user','content':'new notes'}]})
            assert ws.receive_json()=={'type':'chat_context_synced','url':None,'chat_id':'new_chat_123'}
            ws.send_json({'type':'end'})
            assert ws.receive()['type']=='websocket.close'


def test_hands_free_and_modal_both_observe_chat_updates():
    root=Path(__file__).resolve().parents[1]
    free=(root/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text(encoding='utf-8')
    modal=(root/'frontend/src/components/chat/LiveVoiceDialog.tsx').read_text(encoding='utf-8')
    transport=(root/'frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    for source in (free,modal):
        assert 'useApp.subscribe(sync)' in source
        assert 'sendChatContext(' in source
        assert 'repository_handoff' in source
    assert 'type:\'chat_context\'' in transport
    assert 'this.pendingChatContext' in transport
    assert 'history,allowComputer' in free
    assert '[],allowComputer' not in free

def test_spoken_install_request_opens_review_without_model_tool_call(monkeypatch):
    """The local speech-to-chat handoff still works if Gemini forgets to call a tool."""
    from voice import live
    monkeypatch.setattr(live,'gemini_key',lambda:'fake-test-key')
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    class Session:
        def __init__(self):self.history_ready=asyncio.Event()
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def send_client_content(self,**kw):self.history_ready.set()
        async def send_realtime_input(self,**kw):pass
        async def receive(self):
            await self.history_ready.wait()
            yield NS(tool_call=None,server_content=NS(input_transcription=NS(text='يا برق ثبت الريبو ده',finished=True),
                 output_transcription=None,model_turn=None,interrupted=False,turn_complete=False))
            await asyncio.Event().wait()
    session=Session()
    google=ModuleType('google');genai=ModuleType('google.genai')
    genai.types=NS(Blob=lambda **kw:kw,FunctionResponse=lambda **kw:kw)
    genai.Client=lambda **kw:NS(aio=NS(live=NS(connect=lambda **kw:session),aclose=lambda:asyncio.sleep(0)))
    google.genai=genai
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules,'google',google);mp.setitem(sys.modules,'google.genai',genai)
        app=FastAPI();app.websocket('/live')(live.handle_live)
        with TestClient(app).websocket_connect('/live?mode=open') as ws:
            assert ws.receive_json()['type']=='ready'
            ws.send_json({'type':'context','messages':[],
                          'reference_messages':[{'role':'user','content':TRACKED}]})
            found=[]
            for _ in range(4):
                event=ws.receive_json();found.append(event)
                if event['type']=='repository_handoff':break
            assert {'type':'repository_handoff','url':URL} in found
            # A preview is the only allowed action; never downloads or installs.
            ws.send_json({'type':'end'})
            assert ws.receive()['type']=='websocket.close'


def test_pasted_tracking_url_opens_repository_review_in_text_chat():
    source=(Path(__file__).resolve().parents[1]/'frontend/src/lib/chat.ts').read_text()
    assert 'utm_source=chatgpt.com' in source
    assert 'const directLink=' in source
    assert "tab:'github'" in source
    assert 'openWorkspaceSafely();' in source
