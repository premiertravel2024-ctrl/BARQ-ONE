from voice.app_tools import LIVE_APP_TOOLS
from voice.brain_bridge import LIVE_BARQ_TOOLS
"""Opt-in natural voice contract: no wake word, no tools by default; actions with consent."""
import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ('voice_computer_requested', 'saved_desktop_permission'),
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_open_conversation_two_realtime_audio_replies_and_policy_gate(
        monkeypatch, voice_computer_requested, saved_desktop_permission):
    from voice import live
    from computer_control import api as computer_api
    from computer_control.safety.policy import Policy
    # NEVER depend on the developer's real, persisted desktop-control setting.
    # On Windows that setting may be enabled, while this test used to assume
    # computer_enabled=False regardless of the user granting access.
    monkeypatch.setattr(computer_api, 'load_policy',
                        lambda: Policy(enabled=saved_desktop_permission))
    # Model Windows' opt-in check independent of the OS running pytest.
    monkeypatch.setattr(live, 'enabled_on_platform', lambda flag: bool(flag))
    tools_allowed = voice_computer_requested and saved_desktop_permission
    monkeypatch.delenv('LOCAL_ONLY', raising=False)
    monkeypatch.setattr(live, 'gemini_key', lambda: 'simulated-key')
    class Session:
        def __init__(self):
            self.q=asyncio.Queue(); self.context=[]; self.inputs=[]
        async def __aenter__(self):return self
        async def __aexit__(self,*_):pass
        async def send_client_content(self,**kwargs):self.context.append(kwargs)
        async def send_realtime_input(self,**kwargs):
            self.inputs.append(kwargs)
            if kwargs.get('audio'):
                await self.q.put(NS(tool_call=None, server_content=NS(
                    interrupted=False, input_transcription=NS(text='إزيك'),
                    output_transcription=NS(text='أيوه يا أشرف'),
                    model_turn=NS(parts=[NS(inline_data=NS(data=b'\x00\x00'))]),
                    turn_complete=True)))
        async def receive(self): yield await self.q.get()
    session=Session(); configs=[]
    google=ModuleType('google'); genai=ModuleType('google.genai')
    class Blob:
        def __init__(self,data,mime_type):self.data,self.mime_type=data,mime_type
    genai.types=NS(Blob=Blob)
    def connect(**kwargs):configs.append(kwargs['config']);return session
    genai.Client=lambda **kw:NS(aio=NS(live=NS(connect=connect),aclose=lambda:asyncio.sleep(0)))
    google.genai=genai
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules,'google',google);mp.setitem(sys.modules,'google.genai',genai)
        app=FastAPI();app.websocket('/live')(live.handle_live)
        call_url='/live?mode=open&computer='+('1' if voice_computer_requested else '0')
        with TestClient(app).websocket_connect(call_url) as ws:
            assert ws.receive_json()['computer_enabled'] is tools_allowed
            ws.send_json({'type':'context','messages':[]})
            for i in range(2):
                ws.send_bytes(b'\x03\x00'*100)
                events={}
                while len(events)<(5 if i==0 else 4):
                    msg=ws.receive_json();events[msg['type']]=msg
                assert {'input_text','output_text','audio','turn_complete'} <= events.keys()
                if i==0:assert 'audio_relay' in events
                assert events['output_text']['text']=='أيوه يا أشرف'
            ws.send_json({'type':'end'})
            assert ws.receive()['type']=='websocket.close'
    assert len(session.inputs)==2
    assert all('audio' in kwargs and not kwargs.get('audio_stream_end') for kwargs in session.inputs)
    assert len(configs)==1
    cfg=configs[0]
    from voice.public_tools import LIVE_PUBLIC_TOOLS
    from voice.computer_tools import LIVE_COMPUTER_TOOLS
    from voice.live import LIVE_REPOSITORY_TOOLS
    # Public info and repository *preview* tools are available in every call;
    # only audited desktop-control tools require both explicit permissions.
    assert cfg['tools']==LIVE_BARQ_TOOLS + LIVE_PUBLIC_TOOLS + LIVE_REPOSITORY_TOOLS + LIVE_APP_TOOLS + (LIVE_COMPUTER_TOOLS if tools_allowed else [])
    assert 'prepare_github_repository' in str(cfg['tools'])
    assert ('open_on_computer' in str(cfg['tools'])) is tools_allowed
    assert cfg['realtime_input_config']['automatic_activity_detection']['silence_duration_ms']==900
    assert cfg['history_config']['initial_history_in_client_content'] is True
    assert 'مش لازم يقول اسمك' in cfg['system_instruction']


def test_frontend_open_mode_is_explicit_and_disable_computer_tools():
    base=Path(__file__).resolve().parents[1]
    handsfree=(base/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text(encoding='utf-8')
    settings=(base/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    app=(base/'frontend/src/App.tsx').read_text(encoding='utf-8')
    client=(base/'frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    # Open conversation must receive the actual linked chat, not [] (the old bug).
    assert "await voice.start(state.voiceId,history,allowComputer,linkedChat.current||'',false,true)" in handsfree
    assert 'live.current?.sendChatContext(' in handsfree
    assert "message.type==='repository_handoff'" in handsfree
    assert 'computer_enabled' in handsfree and 'launch_approval' in handsfree
    assert 'allowComputerInConversation' in settings
    assert "window.addEventListener('barq-handsfree-start',onStart)" in handsfree
    assert 'برق الصوتي الدائم — مع بدء Windows' in settings
    assert '<HandsFreeVoice/>' in app
    assert '!isHandsFreeActive()' in app
    # Local voice activity detection now finalizes phrases in open conversation too.
    # Prevent the old assertion from requiring the broken open-mode exception.
    assert "if(socket.readyState===WebSocket.OPEN)" in client
    assert "type:'end_audio'" in client
    assert "this.detectEndOfSpeech(frame,socket" in client
    assert "&&!this.openConversation" not in client
    assert "&mode=${openConversation?'open':'standard'}" in client
