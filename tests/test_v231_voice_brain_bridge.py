"""Faked Gemini Live: only VERIFIED speech can enter BARQ's own execution brain."""
import asyncio
from types import SimpleNamespace as NS
import sys
import types

import pytest

from voice.brain_bridge import BARQVoiceBrain, safe_cloud_view, audit_unverified_live_claim, has_verified_completion
from voice.command_guard import VoiceCommandGate
from voice.search_hub import SearchHub, classify_scope


@pytest.mark.asyncio
async def test_phase1_open_notepad_ignores_model_authored_target():
    sent=[]
    async def dispatcher(name,args,cid):
        sent.append((name,args,cid))
        return {'status':'opened','message':'اتفتحت المفكرة على الجهاز.'}
    brain=BARQVoiceBrain(dispatcher=dispatcher)
    gate=VoiceCommandGate();gate.record('يا برق، افتح المفكرة')
    result=await brain.ask(gate,{'request':'امسح ملفات الجهاز'},conversation_id='chat-1',computer_enabled=True)
    assert result['status']=='opened' and 'المفكرة' in result['spoken_ar']
    assert sent==[('open_on_computer',{'request':'يا برق، افتح المفكرة'},'chat-1')]
    assert not (await brain.ask(gate,{},computer_enabled=True))['status']=='opened'
    assert safe_cloud_view(result)['cards']==[]


@pytest.mark.asyncio
async def test_phase1_search_invoice_results_only_in_local_cards():
    sent=[]
    async def dispatcher(name,args,cid):
        sent.append((name,args))
        return {'status':'ok','results':[{'name':'فاتورة-123.pdf','extension':'pdf'}], 'message':'Search complete'}
    brain=BARQVoiceBrain(dispatcher=dispatcher)
    gate=VoiceCommandGate();gate.record('دور على ملف فاتورة')
    value=await brain.ask(gate,{'request':'send secrets to web'},computer_enabled=True)
    assert value['status']=='ok' and value['cards'][0]['label']=='فاتورة-123.pdf'
    assert value['spoken_ar']=='لقيت 1 نتيجة. التفاصيل ظهرت جوه برق على الشاشة.'
    assert 'فاتورة-123.pdf' not in str(safe_cloud_view(value))
    assert sent[0][0]=='search_device_files'


@pytest.mark.asyncio
async def test_phase1_model_cannot_act_without_fresh_speech_or_with_negation():
    sent=[]
    async def dispatcher(*args):sent.append(args);return {'status':'opened'}
    brain=BARQVoiceBrain(dispatcher=dispatcher)
    gate=VoiceCommandGate()
    assert (await brain.ask(gate,{'request':'افتح المفكرة'},computer_enabled=True))['status']=='needs_clarification'
    gate.record('لو قلت افتح المفكرة ده مجرد مثال')
    assert (await brain.ask(gate,{'request':'افتح المفكرة'},computer_enabled=True))['status']=='needs_clarification'
    assert sent==[]
    assert audit_unverified_live_claim('فتحت المفكرة',False)
    assert audit_unverified_live_claim('درجة حرارة المعالج 65 درجة',False)
    assert not audit_unverified_live_claim('فتحت المفكرة',True)


@pytest.mark.asyncio
async def test_search_scope_privacy_and_ephemeral_ordinals():
    hub=SearchHub(now=lambda:100.0)
    assert classify_scope('دور على ملف فاتورة')=='device'
    assert classify_scope('دور على GitHub')=='github'
    assert classify_scope('الطقس في الرياض')=='weather'
    assert classify_scope('دور في شاتاتي')=='chats'
    blocked=await hub.search('دور على كلمة السر في ملفي',scope='web',computer_enabled=True)
    assert blocked['status']=='denied'
    hub.remember('device',[{'label':'one.pdf','kind':'device'},{'label':'two.pdf','kind':'device'}])
    assert (await hub.followup('افتح التاني'))['status']=='needs_approval'
    assert (await hub.followup('افتح التالت'))['status']=='needs_clarification'
    hub.now=lambda:300.0
    assert (await hub.followup('افتح التاني'))['status']=='expired'


def test_gemini_live_fake_script_transcript_open_then_search(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from voice import live
    import google
    calls=[]
    class FakeSession:
        async def __aenter__(self):self.wait=asyncio.Event();return self
        async def __aexit__(self,*args):pass
        async def send_client_content(self,**kwargs):pass
        async def send_realtime_input(self,**kwargs):pass
        async def send_tool_response(self,**kwargs):
            calls.extend(kwargs['function_responses'])
        async def receive(self):
            for i,(speech,query) in enumerate([
                ('يا برق، افتح المفكرة','ignore this model request'),
                ('دور على ملف فاتورة','model asked to delete all files')]):
                def transcript(text, finished):
                    return NS(tool_call=None,server_content=NS(input_transcription=NS(text=text,finished=finished),
                        output_transcription=None,model_turn=None,interrupted=False,turn_complete=False))
                first, last = speech.rsplit(' ', 1)
                yield transcript(first, False)
                yield NS(tool_call=NS(function_calls=[NS(id=str(i),name='ask_barq',args={'request':query})]),server_content=None)
                yield transcript(last, True)
                yield NS(tool_call=None,server_content=NS(input_transcription=None,output_transcription=None,model_turn=None,interrupted=False,turn_complete=True))
            await self.wait.wait()
    class FakeClient:
        def __init__(self,**kwargs):self.aio=NS(live=NS(connect=self.connect),aclose=self.close)
        def connect(self,**kwargs):return FakeSession()
        async def close(self):pass
    fake=types.ModuleType('google.genai')
    fake.Client=FakeClient
    fake.types=NS(FunctionResponse=lambda **kwargs:NS(**kwargs))
    monkeypatch.setitem(sys.modules,'google.genai',fake)
    monkeypatch.setattr(google,'genai',fake,raising=False)
    monkeypatch.setattr(live,'gemini_key',lambda:'mock-key')
    monkeypatch.setattr(live,'enabled_on_platform',lambda yes:bool(yes))
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    from computer_control import api as control_api
    from computer_control.safety.policy import Policy
    monkeypatch.setattr(control_api,'load_policy',lambda:Policy(enabled=True))
    async def fake_dispatch(name,args,conv):
        if name=='search_device_files':return {'status':'ok','results':[{'name':'فاتورة-ديسمبر.pdf','extension':'pdf'}]}
        assert name=='open_on_computer' and args['request']=='يا برق، افتح المفكرة'
        return {'status':'opened','message':'اتفتحت المفكرة.'}
    monkeypatch.setattr(live,'BARQVoiceBrain',lambda:BARQVoiceBrain(dispatcher=fake_dispatch))
    app=FastAPI();app.websocket('/live')(live.handle_live)
    with TestClient(app).websocket_connect('/live?computer=1&conversation_id=chat_1') as ws:
        seen=[]
        for _ in range(16):
            item=ws.receive_json();seen.append(item)
            if len(calls)==2 and any(event.get('type')=='barq_cards' for event in seen):break
        ws.send_json({'type':'end'})
    assert len(calls)==2
    assert calls[0].response['status']=='opened'
    assert calls[1].response['status']=='ok'
    assert calls[1].response['cards']==[]
    assert any(event.get('type')=='barq_cards' and event['cards'][0]['label']=='فاتورة-ديسمبر.pdf' for event in seen)


@pytest.mark.asyncio
async def test_private_followup_never_speaks_file_name_to_gemini():
    hub=SearchHub(now=lambda:100.0)
    hub.remember('device',[{'label':'client-contract-SECRET.pdf','kind':'device'}])
    brain=BARQVoiceBrain(hub=hub)
    gate=VoiceCommandGate();gate.record('اقرأ الأول')
    result=await brain.ask(gate,computer_enabled=False)
    assert 'client-contract-SECRET' not in str(safe_cloud_view(result))
    assert 'client-contract-SECRET' in result['cards'][0]['label']


def test_pending_or_blocked_result_does_not_count_as_verified_success():
    for status in ('started','pending','needs_review','needs_approval','denied','unavailable','needs_clarification'):
        assert not has_verified_completion(status)
    assert has_verified_completion('opened')
