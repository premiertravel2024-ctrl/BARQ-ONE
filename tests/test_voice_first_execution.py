"""Voice-first regressions: decoded speech -> brain -> dispatch -> evidence.

No real microphone, cloud ASR or Windows GUI is available on this host.
"""
import asyncio
import pytest
from voice.brain_bridge import BARQVoiceBrain, action_route, safe_cloud_view
from voice.command_guard import VoiceCommandGate
from voice.intent import setting_request
from voice.local_speaker import local_audio_command

@pytest.mark.parametrize('speech,route',[
 ('يا برق افتح المفكرة','open_on_computer'),
 ('ممكن تفتح المفكرة','open_on_computer'),
 ('افتح كروم وبعدين اكتب عنوان الموقع','start_computer_task'),
 ('دور على ملف وانقله للتنزيلات','start_computer_task'),
 ('اعمل تقرير عن CPU واحفظه','start_computer_task'),
 ('ابنيلي برنامج حسابات واديني exe','start_coding_task'),
 ('عاوزك تعمللي تطبيق للمبيعات','start_coding_task'),
 ('افتح برنامج stop watch','open_on_computer'),
 ('افتح الملف الثاني','followup'),
 ('كمل','continue_current_work'),
 ('حرارة المعالج كام','get_pc_system_facts'),
 ('دور على ملف فاتورة','search_hub'),
 ('اقفل كروم','start_computer_task'),
 ('انسخ الملف للتنزيلات','start_computer_task'),
 ('وقف المهمة','stop_computer_task'),
])
def test_routes(speech,route):assert action_route(speech)==route

@pytest.mark.parametrize('speech,args',[
 ('ظبط الصوت على 35 في المية',{'setting':'volume','action':'set','percent':35}),
 ('خلي سطوع الشاشة ٦٠',{'setting':'brightness','action':'set','percent':60}),
 ('علي صوت الجهاز شوية',{'setting':'volume','action':'up','percent':10}),
 ('قلل الصوت 15',{'setting':'volume','action':'down','percent':15}),
 ('مستوى الصوت كام',{'setting':'volume','action':'get'}),
 ('set volume to 0',{'setting':'volume','action':'set','percent':0}),
])
def test_setting_values(speech,args):assert setting_request(speech)==args

@pytest.mark.parametrize('speech',['ظبط الصوت 101','خلي السطوع -2','ظبط الصوت 2.5','ظبط الصوت','علي الصوت 99','وطي الصوت وزود الصوت','ظبط الصوت 20 او 30'])
def test_ambiguous_setting_never_changes_a_level(speech):assert setting_request(speech).get('error')

@pytest.mark.asyncio
@pytest.mark.parametrize('speech',['متقفلش كروم','متنقلش الملف','لا تحذف الملف','ازاي افتح كروم','اشرح ازاي ابني برنامج','لو طلبت منك افتح المفكرة','do not open Chrome'])
async def test_questions_negations_never_dispatch(speech):
 calls=[]
 async def dispatch(*args):calls.append(args);return {'status':'opened'}
 gate=VoiceCommandGate();gate.record(speech)
 result=await BARQVoiceBrain(dispatcher=dispatch).ask(gate,computer_enabled=True)
 assert result['status']=='needs_clarification' and not calls

@pytest.mark.asyncio
async def test_local_audio_to_dispatch_and_returned_evidence():
 calls=[]
 async def decode(blob):
  assert blob.startswith(b'RIFF')
  return 'ظبط الصوت على ٣٥'
 async def dispatch(name,args,cid):
  calls.append((name,args))
  return {'status':'ok','message':'مستوى الصوت بقى 35 بالمية.'}
 result=await local_audio_command(b'RIFF'+bytes(1000),transcriber=decode,
     brain=BARQVoiceBrain(dispatcher=dispatch),computer_enabled=True)
 assert result['status']=='ok'
 assert calls==[('control_windows_setting',{'setting':'volume','action':'set','percent':35})]
 assert '35' in result['spoken_ar']

@pytest.mark.asyncio
async def test_exact_launcher_approval_survives_bridge_and_is_private():
 async def dispatch(*args):
  return {'status':'approval_required','message':'محتاج موافقة','_ui':{
      'candidate_id':'candidate-1','approval_token':'private-token','label':'Notepad'}}
 gate=VoiceCommandGate();gate.record('افتح المفكرة')
 result=await BARQVoiceBrain(dispatcher=dispatch).ask(gate,computer_enabled=True)
 assert result['needs_approval'] and result['_ui']['type']=='launch_approval'
 assert result['_ui']['approval_token']=='private-token'
 assert 'private-token' not in str(safe_cloud_view(result))
 assert (await BARQVoiceBrain(dispatcher=dispatch).ask(gate,computer_enabled=True))['status']=='needs_clarification'

@pytest.mark.asyncio
async def test_coding_goes_to_same_chat_once_without_desktop_click_planner():
 async def forbidden(*args):raise AssertionError('coding must use chat engine')
 gate=VoiceCommandGate();gate.record('ابنيلي برنامج حسابات واديني exe')
 brain=BARQVoiceBrain(dispatcher=forbidden)
 result=await brain.ask(gate,{'request':'delete everything'},conversation_id='chat-1',computer_enabled=True)
 assert result['status']=='requested'
 assert result['_ui']['text']=='ابنيلي برنامج حسابات واديني exe'
 assert result['_ui']['conversation_id']=='chat-1'
 assert result['_ui']['request_id']
 assert '_ui' not in safe_cloud_view(result)
 assert (await brain.ask(gate,computer_enabled=True))['status']=='needs_clarification'
 gate.record('ابنيلي برنامج')
 assert (await brain.ask(gate,computer_enabled=False))['status']=='permission_required'

@pytest.mark.asyncio
async def test_consent_off_and_stale_speech_do_not_execute():
 calls=[]
 async def dispatch(*args):calls.append(args);return {'status':'opened'}
 brain=BARQVoiceBrain(dispatcher=dispatch)
 gate=VoiceCommandGate();gate.record('افتح كروم',now=100)
 assert (await brain.ask(gate,computer_enabled=True,now=121))['status']=='needs_clarification'
 gate.record('افتح كروم')
 assert (await brain.ask(gate,computer_enabled=False))['status']=='permission_required'
 assert not calls

@pytest.mark.parametrize('speech,expected_event',[
 ('ابنيلي برنامج حسابات واديني exe','chat_task_requested'),
 ('افتح المفكرة','launch_approval'),
 ('ظبط الصوت على 35','barq_task'),
])
def test_live_transcript_to_private_ui_event(monkeypatch,speech,expected_event):
 import sys
 import types
 from threading import Event
 from types import SimpleNamespace as NS
 import google
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from voice import live
 from computer_control import api as control_api
 from computer_control.safety.policy import Policy
 replies=[];dispatched=[]
 tool_response_sent=Event()
 class Session:
  async def __aenter__(self):self.wait=asyncio.Event();return self
  async def __aexit__(self,*args):pass
  async def send_client_content(self,**kwargs):pass
  async def send_realtime_input(self,**kwargs):pass
  async def send_tool_response(self,**kwargs):
   replies.extend(kwargs['function_responses'])
   tool_response_sent.set()
  async def receive(self):
   yield NS(tool_call=None,server_content=NS(input_transcription=NS(text=speech,finished=True),output_transcription=None,model_turn=None,interrupted=False,turn_complete=False))
   yield NS(tool_call=NS(function_calls=[NS(id='call-1',name='ask_barq',args={'request':'untrusted different goal'})]),server_content=None)
   await self.wait.wait()
 class Client:
  def __init__(self,**kwargs):self.aio=NS(live=NS(connect=lambda **kw:Session()),aclose=self.close)
  async def close(self):pass
 fake=types.ModuleType('google.genai');fake.Client=Client;fake.types=NS(FunctionResponse=lambda **kw:NS(**kw))
 monkeypatch.setitem(sys.modules,'google.genai',fake);monkeypatch.setattr(google,'genai',fake,raising=False)
 monkeypatch.setattr(live,'gemini_key',lambda:'fake')
 monkeypatch.setattr(live,'enabled_on_platform',lambda value:bool(value))
 monkeypatch.delenv('LOCAL_ONLY',raising=False)
 monkeypatch.setattr(control_api,'load_policy',lambda:Policy(enabled=True))
 async def dispatch(name,args,cid):
  dispatched.append((name,args,cid))
  if name=='open_on_computer':
   return {'status':'approval_required','message':'محتاج موافقة','_ui':{'candidate_id':'verified-candidate','approval_token':'private-exact-token','label':'المفكرة'}}
  assert name=='control_windows_setting' and args['percent']==35
  return {'status':'ok','message':'تم ضبط مستوى الصوت 35.'}
 monkeypatch.setattr(live,'BARQVoiceBrain',lambda:BARQVoiceBrain(dispatcher=dispatch))
 app=FastAPI();app.websocket('/live')(live.handle_live)
 events=[]
 with TestClient(app).websocket_connect('/live?computer=1&conversation_id=chat_1') as ws:
  while True:
   event=ws.receive_json();events.append(event)
   if event['type']=='barq_task':break
  assert tool_response_sent.wait(timeout=5), 'Live session did not return the tool response'
  ws.send_json({'type':'end'})
  assert ws.receive()['type']=='websocket.close'
 match=next(event for event in events if event['type']==expected_event)
 if expected_event=='chat_task_requested':
  assert match['text']==speech and match['conversation_id']=='chat_1'
  assert not dispatched
 elif expected_event=='launch_approval':
  assert match['approval_token']=='private-exact-token'
 else:assert match['status']=='ok'
 assert replies and '_ui' not in replies[0].response
 assert 'private-exact-token' not in str(replies[0].response)


def test_tray_pause_stops_live_capture_and_persists_mute(monkeypatch):
 from unittest.mock import Mock
 from pathlib import Path
 from voice.background_window import BackgroundWindow
 from voice import wake
 calls=[]
 monkeypatch.setattr(wake,'set_wake_enabled_from_tray',lambda enabled:calls.append(('enabled',enabled)))
 monkeypatch.setattr(wake,'stop_listener',lambda:calls.append(('stop',)))
 window=Mock()
 BackgroundWindow(window,Path('unused.png')).pause()
 assert calls==[('enabled',False),('stop',)]
 window.evaluate_js.assert_called_once_with("window.dispatchEvent(new Event('barq-handsfree-stop'))")
