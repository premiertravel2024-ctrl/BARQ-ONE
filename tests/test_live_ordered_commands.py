"""Exercise the live server with late ASR packets and no model tool call."""
import asyncio
from io import BytesIO
import sys
from types import ModuleType, SimpleNamespace as NS
import wave

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from voice.brain_bridge import BARQVoiceBrain
from voice.intent import setting_request
from voice.search_hub import SearchHub


def packet(*, text=None, finished=None, spoken=None, complete=False):
    return NS(tool_call=None, server_content=NS(
        input_transcription=NS(text=text,finished=finished) if text is not None else None,
        output_transcription=NS(text=spoken) if spoken else None,
        model_turn=None, interrupted=False, turn_complete=complete,
    ))


@pytest.mark.parametrize('tool_timing', ['none', 'before_transcript', 'after_transcript', 'after_boundary'])
def test_direct_voice_command_runs_once_when_gemini_only_talks(monkeypatch, tool_timing):
    from voice import live, live_turn, gemini
    from computer_control import api
    from computer_control.safety.policy import Policy

    actions = []
    replies = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self,*args):
            pass

        async def send_tool_response(self, *, function_responses):
            replies.extend(function_responses)

        async def receive(self):
            yield packet(text='بص يا برق، افتحلي فولدر', finished=False)
            if tool_timing == 'before_transcript':
                yield NS(tool_call=NS(function_calls=[NS(name='ask_barq',id='early',args={})]),server_content=None)
                while not replies:
                    await asyncio.sleep(0.001)
            if tool_timing == 'after_transcript':
                yield NS(tool_call=NS(function_calls=[
                    NS(name='open_on_computer',id='legacy',args={'request':'افتح فولدر IATA REPORT'}),
                    NS(name='ask_barq',id='brain',args={}),
                ]),server_content=None)
            if tool_timing == 'after_boundary':
                yield packet(complete=True)
            yield packet(text=' IATA REPORT', finished=True)
            # Give the direct dispatcher a chance to act before any model response.
            for _ in range(100):
                if actions:
                    break
                await asyncio.sleep(0.001)
            assert actions, 'A finished transcript must reach BARQ before Gemini replies'
            if tool_timing != 'after_boundary':
                yield packet(spoken='هفتح الفولدر بعدين')
                yield packet(complete=True)
            await asyncio.Event().wait()

    async def dispatch(name,args,chat):
        actions.append((name,args,chat))
        return {'status':'opened','message':'فتحته على الجهاز.'}

    async def synthesize(text, voice):
        assert text=='فتحته على الجهاز.'
        with BytesIO() as stream:
            with wave.open(stream,'wb') as clip:
                clip.setparams((1,2,24000,0,'NONE','not compressed'))
                clip.writeframes(b'\x01\x02')
            return stream.getvalue(),'audio/wav'

    import google
    fake=ModuleType('google.genai')
    fake.Client=lambda **kw:NS(aio=NS(live=NS(connect=lambda **kw:Session()),aclose=lambda:asyncio.sleep(0)))
    fake.types=NS(FunctionResponse=lambda **kwargs:NS(**kwargs))
    monkeypatch.setitem(sys.modules,'google.genai',fake)
    monkeypatch.setattr(google,'genai',fake,raising=False)
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    monkeypatch.setattr(live,'gemini_key',lambda:'fake-key')
    monkeypatch.setattr(live_turn,'TRANSCRIPT_GRACE',0.1)
    async def unexpected_legacy_dispatch(*args):
        pytest.fail('The legacy tool must reuse the direct result')
    monkeypatch.setattr(live,'dispatch_computer_tool',unexpected_legacy_dispatch)
    monkeypatch.setattr(live,'enabled_on_platform',bool)
    monkeypatch.setattr(api,'load_policy',lambda:Policy(enabled=True))
    monkeypatch.setattr(live,'BARQVoiceBrain',lambda:BARQVoiceBrain(dispatcher=dispatch))
    monkeypatch.setattr(gemini,'synthesize_speech',synthesize)

    app=FastAPI()
    app.websocket('/live')(live.handle_live)
    with TestClient(app).websocket_connect('/live?computer=1&conversation_id=chat1') as ws:
        events=[ws.receive_json() for _ in range(7+int(tool_timing == 'before_transcript'))]
        if tool_timing == 'after_transcript':
            assert [reply.response['status'] for reply in replies]==['opened','opened']
        ws.send_json({'type':'end'})
    assert {event['type'] for event in events}=={
        'ready','input_text','barq_task','verified_output_text','turn_complete','audio',
    }
    if tool_timing == 'before_transcript':
        assert replies[0].response['status']=='needs_clarification'
    assert actions==[('open_on_computer',{'request':'بص يا برق، افتحلي فولدر IATA REPORT'},'chat1')]
    assert next(event for event in events if event['type']=='audio')['data']=='AQI='


@pytest.mark.asyncio
async def test_egyptian_filename_search_preserves_extension_and_stays_local():
    requests=[]
    async def local(name,args):
        requests.append((name,args))
        return {'status':'ok','results':[{'name':'IATA-11.xlsx','id':'exact-id'}]}
    hub=SearchHub()
    result=await hub.search('بقولك إيه يا برق، ممكن تدورلي على ملف IATA-11.xlsx عندي',
                            local_dispatch=local,computer_enabled=True)
    assert requests==[('search_device_files',{'query':'IATA-11.xlsx'})]
    assert result['cards'][0]['id']=='exact-id'


@pytest.mark.parametrize('speech,percent', [
    ('معلش ظبطلي الصوت على خمسة وتلاتين في المية',35),
    ('خلي سطوع الشاشة على النص',50),
    ('ظبط الصوت على واحد في المية',1),
])
def test_settings_accept_spoken_egyptian_percentages(speech,percent):
    assert setting_request(speech)['percent']==percent


def test_typed_or_spoken_launch_preserves_literal_windows_path():
    from launcher.nlu import parse
    path=r'C:\Reports\IATA-11.xlsx'
    assert parse('يا برق لو سمحت ممكن تفتحلي '+path).target_text==path
    assert parse('متفتحش '+path) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('names,status', [
    (['BARQ-Test.txt'], 'opened'),
    (['BARQ-Test.txt','BARQ-Test.txt'], 'choose'),
    (['BARQ-Test-old.txt'], 'choose'),
    ([], 'not_found'),
])
async def test_voice_search_and_open_only_opens_one_exact_candidate(monkeypatch,names,status):
    from launcher import api as launcher_api
    from voice.command_guard import VoiceCommandGate

    launches=[]
    def launch(candidate_id):
        launches.append(candidate_id)
        return {'status':'opened'}
    monkeypatch.setattr(launcher_api,'_launch',launch)

    async def dispatch(tool,args,chat):
        assert tool=='search_device_files'
        assert args=={'query':'BARQ-Test.txt'}
        return {'status':'ok','results':[{'name':name,'id':str(i)} for i,name in enumerate(names)]}

    brain=BARQVoiceBrain(dispatcher=dispatch)
    gate=VoiceCommandGate()
    speech='دور على ملف BARQ-Test.txt وافتحه'
    assert brain.is_direct_turn(speech)
    gate.record(speech)
    result=await brain.ask(gate,computer_enabled=True)
    assert result['status']==status
    assert launches==(['0'] if status=='opened' else [])
    if len(names)==2:
        gate.record('افتح رقم ٢')
        result=await brain.ask(gate,computer_enabled=True)
        assert result['status']=='opened'
        assert launches==['1']
