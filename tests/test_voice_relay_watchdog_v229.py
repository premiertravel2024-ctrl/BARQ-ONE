"""Voice transport diagnostics use no cloud service, microphone, or user secrets."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace as NS
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_live_stream_acknowledges_forwarded_audio_without_user_payload(monkeypatch):
    from voice import live
    monkeypatch.delenv('LOCAL_ONLY', raising=False)
    monkeypatch.setattr(live,'gemini_key',lambda:'fake-local-test-key')
    class FakeSession:
        def __init__(self):
            self.received=[]
            self.q=asyncio.Queue()
        async def __aenter__(self):return self
        async def __aexit__(self,*a):return None
        async def send_client_content(self,**kwargs):pass
        async def send_realtime_input(self,**kwargs):
            self.received.append(kwargs)
            if kwargs.get('audio'):
                await self.q.put(NS(server_content=NS(interrupted=False,input_transcription=NS(text='يا برق'),
                    output_transcription=NS(text='أيوه'),model_turn=NS(parts=[]),turn_complete=True)))
        async def receive(self):
            yield await self.q.get()
    session=FakeSession()
    fake_google=ModuleType('google')
    fake_genai=ModuleType('google.genai')
    class Blob:
        def __init__(self,data,mime_type):self.data,self.mime_type=data,mime_type
    fake_genai.types=NS(Blob=Blob)
    fake_genai.Client=lambda **kw:NS(aio=NS(live=NS(connect=lambda **kw:session),aclose=lambda:asyncio.sleep(0)))
    fake_google.genai=fake_genai
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules,'google',fake_google)
        mp.setitem(sys.modules,'google.genai',fake_genai)
        app=FastAPI();app.websocket('/test')(live.handle_live)
        with TestClient(app).websocket_connect('/test') as ws:
            assert ws.receive_json()['type']=='ready'
            ws.send_json({'type':'context','messages':[]})
            ws.send_bytes(b'\x01\x00')
            events=[]
            while len(events)<4:
                events.append(ws.receive_json())
            types=[e['type'] for e in events]
            assert 'audio_relay' in types
            assert 'input_text' in types and 'output_text' in types
            acknowledgment=next(e for e in events if e['type']=='audio_relay')
            assert acknowledgment=={'type':'audio_relay','state':'forwarded'}
            ws.send_json({'type':'end'})
            ws.receive()
    assert session.received[0]['audio'].data==b'\x01\x00'


def test_client_silence_warnings_do_not_auto_authorize_tools():
    from pathlib import Path
    code=Path('frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    assert "type:'voice_warning'" in code
    assert 'audio_relay' in code
    assert 'this.watchdog' in code
    assert "this.firstVoiceAt=0" in code.split("if(event.type==='turn_complete'){",1)[1].split("}",1)[0]
    assert "'computer'" not in code.split('this.watchdog=setInterval(',1)[1].split('},2000)',1)[0]
