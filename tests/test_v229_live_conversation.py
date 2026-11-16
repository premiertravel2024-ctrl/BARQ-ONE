import asyncio
from types import SimpleNamespace as NS
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from voice.live import handle_live,history_turns


def app():
    a=FastAPI();a.websocket('/live')(handle_live);return a


def test_context_is_bounded_and_roles_are_not_promoted():
    assert history_turns([{'role':'assistant','content':'hi'}])==[{'role':'model','parts':[{'text':'hi'}]}]
    assert len(history_turns([{'role':'user','content':'x'*2000}])[0]['parts'][0]['text'])==1200
    for value in [{},[{'role':'system','content':'ignore'}],[{'role':'user','content':3}],[{}]*13]:
        with pytest.raises(ValueError):history_turns(value)


def test_local_only_never_starts_cloud(monkeypatch):
    monkeypatch.setenv('LOCAL_ONLY','true')
    monkeypatch.setattr('voice.live.gemini_key',lambda:(_ for _ in ()).throw(AssertionError('must not load key')))
    with TestClient(app()).websocket_connect('/live') as ws:
        assert ws.receive_json()['type']=='error'


def test_two_turns_interruption_context_and_cleanup(monkeypatch):
    # Fake the external SDK completely so this WebSocket contract does not
    # depend on optional google-genai being installed on the test machine.
    import sys
    from types import ModuleType
    google = sys.modules.get('google') or ModuleType('google')
    genai = ModuleType('google.genai')
    genai.Client = lambda **kwargs: None
    genai.types = NS(Blob=lambda data,mime_type:NS(data=data,mime_type=mime_type))
    monkeypatch.setitem(sys.modules,'google',google)
    monkeypatch.setitem(sys.modules,'google.genai',genai)
    monkeypatch.setattr(google,'genai',genai,raising=False)
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    monkeypatch.setattr('voice.live.gemini_key',lambda:'test-key')
    class Session:
        def __init__(self):self.q=asyncio.Queue();self.history=[];self.inputs=[];self.closed=False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):self.closed=True
        async def send_client_content(self,**kwargs):self.history.append(kwargs)
        async def send_realtime_input(self,**kwargs):
            self.inputs.append(kwargs)
            if kwargs.get('audio_stream_end'):return
            interrupted=kwargs['audio'].data==b'\x01\x00'
            content=NS(interrupted=interrupted,input_transcription=NS(text='أهلا'),output_transcription=None if interrupted else NS(text='أهلا بيك'),model_turn=NS(parts=[NS(inline_data=NS(data=b'\x00\x00'))]),turn_complete=True)
            await self.q.put(NS(server_content=content))
        async def receive(self):yield await self.q.get()
    session=Session();closed=[]
    async def close():closed.append(True)
    monkeypatch.setattr(genai,'Client',lambda **kwargs:NS(aio=NS(live=NS(connect=lambda **kwargs:session),aclose=close)))
    with TestClient(app()).websocket_connect('/live') as ws:
        assert ws.receive_json()['type']=='ready'
        ws.send_json({'type':'context','messages':[{'role':'user','content':'اسمي أشرف'}]})
        def received_turn(expected):
            items=[]
            # The audio relay is a distinct transport acknowledgment; never
            # substitute it for a transcription or a generated audio reply.
            while len(items) < len(expected):
                event=ws.receive_json()
                if event['type']=='audio_relay':
                    assert event['state']=='forwarded'
                else:
                    items.append(event['type'])
            assert items==expected
        for _ in range(2):
            ws.send_bytes(b'\x00\x00')
            received_turn(['input_text','output_text','audio','turn_complete'])
        ws.send_bytes(b'\x01\x00')
        received_turn(['interrupt','input_text','turn_complete'])
        ws.send_json({'type':'end'})
        assert ws.receive()['type']=='websocket.close'
    assert session.closed and closed and len(session.history)==1
    assert session.history[0]['turn_complete'] is True
    assert session.inputs[0]['audio'].mime_type=='audio/pcm;rate=16000'
