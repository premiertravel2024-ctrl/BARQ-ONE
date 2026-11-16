"""BARQ realtime voice regression tests: input turn boundary and return audio, no cloud needed."""
import asyncio
import sys
from types import ModuleType, SimpleNamespace as NS
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_end_of_phrase_and_speaker_probe_are_sent_to_gemini(monkeypatch):
    from voice import live
    monkeypatch.delenv('LOCAL_ONLY', raising=False)
    monkeypatch.setattr(live, 'gemini_key', lambda: 'fake-for-unit-test')
    class FakeSession:
        def __init__(self):
            self.q = asyncio.Queue()
            self.inputs = []
            self.history = []
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def send_client_content(self, **kwargs): self.history.append(kwargs)
        async def send_realtime_input(self, **kwargs):
            self.inputs.append(kwargs)
            if kwargs.get('audio_stream_end') or kwargs.get('text'):
                content = NS(interrupted=False,input_transcription=None,
                    output_transcription=NS(text='أيوه يا أشرف'),
                    model_turn=NS(parts=[NS(inline_data=NS(data=b'\x00\x00'))]),
                    turn_complete=True)
                await self.q.put(NS(tool_call=None,server_content=content))
        async def receive(self):
            yield await self.q.get()
    session = FakeSession()
    google = ModuleType('google')
    genai = ModuleType('google.genai')
    class Blob:
        def __init__(self, data, mime_type): self.data,self.mime_type=data,mime_type
    genai.types = NS(Blob=Blob)
    configs=[]
    def connect(**kw):
        configs.append(kw['config'])
        return session
    genai.Client = lambda **kw: NS(aio=NS(live=NS(connect=connect),aclose=lambda:asyncio.sleep(0)))
    google.genai = genai
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules,'google',google)
        mp.setitem(sys.modules,'google.genai',genai)
        app = FastAPI(); app.websocket('/voice')(live.handle_live)
        with TestClient(app).websocket_connect('/voice') as ws:
            assert ws.receive_json()['type']=='ready'
            ws.send_json({'type':'context','messages':[{'role':'user','content':'أنا أشرف'}]})
            ws.send_bytes(b'\x01\x00'*128)
            assert ws.receive_json()['type']=='audio_relay'
            ws.send_json({'type':'end_audio'})
            events=[ws.receive_json() for _ in range(4)]
            assert {'voice_phase','output_text','audio','turn_complete'}=={event['type'] for event in events}
            assert next(event for event in events if event['type']=='voice_phase')['status']=='utterance_finalized'
            ws.send_json({'type':'probe'})
            events=[ws.receive_json() for _ in range(4)]
            assert {'voice_phase','output_text','audio','turn_complete'}=={event['type'] for event in events}
            assert any(i.get('audio_stream_end') for i in session.inputs)
            assert any(i.get('text')=='يا برق، قول بصوتك: أيوه يا أشرف، أنا سامعك.' for i in session.inputs)
            ws.send_json({'type':'end'})
            assert ws.receive()['type']=='websocket.close'
    assert configs[0]['history_config']['initial_history_in_client_content'] is True
    assert configs[0]['realtime_input_config']['automatic_activity_detection']['silence_duration_ms'] == 1050
    assert session.history and session.history[0]['turn_complete'] is True
    assert session.history[0]['turns'][0]['parts'][0]['text']=='أنا أشرف'


def test_frontend_separates_live_connection_from_mic_and_player():
    from pathlib import Path
    code=Path('frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    dialog=Path('frontend/src/components/chat/LiveVoiceDialog.tsx').read_text(encoding='utf-8')
    assert "type:'end_audio'" in code
    assert 'detectEndOfSpeech' in code
    assert 'socket.bufferedAmount>1000000' in code
    assert "type:'probe'" in code
    assert 'async unlockSpeaker()' in code
    assert 'async unlockMicrophone()' in code
    assert 'اختبر رد برق بدون ميكروفون' not in dialog
    assert 'تفعيل السماعة' in dialog
    assert 'متصل — بفحص الميكروفون' in dialog
