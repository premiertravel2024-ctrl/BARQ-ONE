import asyncio,json,zipfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from services import personal_assistant as p
from computer_control.safety.policy import Policy

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
 monkeypatch.setattr(p,'state_file',lambda name:tmp_path/name)
 monkeypatch.setattr(p,'processes',lambda:set())
 from voice import owner_voice
 monkeypatch.setattr(owner_voice,'state_file',lambda name:tmp_path/name)
 monkeypatch.setattr('voice.background_window.notify',lambda message:None)
 yield

@pytest.mark.parametrize('text,expected',[
 ('جهزني للشغل','routine'),('وضع اللعب','routine'),('شغل روتين الصبح','routine'),('افتح المفضل تقاريري','favorite'),
 ('رجع آخر تغيير','undo'),('وقف الأغنية','media_pause'),('الاغنية اللي بعدها','media_next'),('كمل الاغنية','media_play'),
 ('بلغني لما التنزيل يخلص','download_watch'),('فكرني بالتقرير لما أفتح Outlook','reminder'),
 ('دورلي على الملف اللي مكتوب فيه مبيعات اكتوبر','content'),('ترجم المحدد','translate'),('اشرح الحافظة','explain_clipboard'),('وقف كل حاجة','emergency')])
def test_voice_and_text_classification(text,expected):assert p.classify(text)[0]==expected

def test_preferences_persist_and_routines_reject_shell():
 p.configure(owner_name='أشرف',routines={'شغلي':['افتح Excel','افتح فولدر التقارير']},favorites={'تقاريري':'D:/Reports'})
 assert p.read()['favorites']['تقاريري']=='D:/Reports'
 with pytest.raises(ValueError):p.configure(routines={'bad':['powershell -EncodedCommand abc']})

def test_process_reminder_is_transition_and_once():
 p.watch_process('Outlook','التقرير')
 assert p.tick(names=set(),jobs={})==[]
 assert len(p.tick(names={'outlook.exe'},jobs={}))==1
 assert p.tick(names={'outlook.exe'},jobs={})==[]
 assert len(p.consume_notifications())==1
 assert p.consume_notifications()==[]

def test_running_process_waits_until_next_launch(monkeypatch):
 monkeypatch.setattr(p,'processes',lambda:{'outlook.exe'})
 p.watch_process('Outlook','next launch')
 assert p.tick(names={'outlook.exe'},jobs={})==[]
 p.tick(names=set(),jobs={})
 assert len(p.tick(names={'outlook.exe'},jobs={}))==1

def test_build_completion_deduplicates_across_monitor_restart():
 jobs={'abc':{'name':'Invoice Tool','status':'success'}}
 assert len(p.tick(names=set(),jobs=jobs))==1
 assert p.tick(names=set(),jobs=jobs)==[]

def test_download_disappearing_is_not_success_without_final_file(tmp_path):
 partial=tmp_path/'file.zip.crdownload';partial.write_bytes(b'partial')
 p.add_watch({'kind':'download','target':str(partial),'message':'done'})
 partial.unlink();assert p.tick(names=set(),jobs={})==[]
 partial.with_suffix('').write_bytes(b'complete')
 assert len(p.tick(names=set(),jobs={}))==1

@pytest.mark.asyncio
async def test_disabled_control_never_launches_routine():
 async def launch(*args):pytest.fail('should not launch')
 result=await p.execute('جهزني للشغل',policy=Policy(enabled=False),launcher=launch)
 assert result['status']=='disabled'

@pytest.mark.asyncio
async def test_routine_stops_on_ambiguous_target(monkeypatch):
 import computer_control.api as api
 monkeypatch.setattr(api,'load_policy',lambda:Policy(enabled=True))
 p.configure(routines={'جهزني للشغل':['افتح Excel','افتح فولدر التقارير','افتح Word']})
 calls=[]
 async def launch(name,args,chat):
  calls.append(args['request']);return {'status':'opened' if len(calls)==1 else 'choose','message':'result'}
 result=await p.execute('جهزني للشغل',policy=Policy(enabled=True),launcher=launch)
 assert result['status']=='partial' and len(calls)==2

def test_neural_profile_two_samples_must_agree():
 from voice import owner_voice
 vector=np.zeros(256,dtype=np.float32);vector[0]=1
 owner_voice.save([vector,vector,vector])
 assert owner_voice.matches(b'',embedding=vector)[0]
 other=np.zeros(256,dtype=np.float32);other[1]=1
 assert not owner_voice.matches(b'',embedding=other)[0]
 owner_voice.delete();assert not owner_voice.enrolled()

def test_inconsistent_or_corrupt_speaker_profile_is_rejected():
 from voice import owner_voice
 values=np.eye(256,dtype=np.float32)[:3]
 with pytest.raises(ValueError):owner_voice.save(values)
 owner_voice.state_file('owner_voice.npz').write_bytes(b'broken')
 assert owner_voice.matches(b'',embedding=np.ones(256))[0] is False

def test_real_bundled_model_loads_and_produces_finite_embedding():
 from voice.owner_voice import embed
 samples=(np.sin(np.arange(16000)*.08)*9000).astype('<i2').tobytes()
 value=embed(samples)
 assert value.shape==(256,) and np.isfinite(value).all()
 assert abs(np.linalg.norm(value)-1)<1e-5

def test_xlsx_content_search_extracts_text_without_macros(tmp_path):
 from services.content_index import _read_text
 path=tmp_path/'report.xlsx'
 with zipfile.ZipFile(path,'w') as archive:
  archive.writestr('xl/sharedStrings.xml','<sst xmlns="urn:x"><si><t>مبيعات أكتوبر</t></si></sst>')
 text=_read_text(path,path.stat().st_size)
 assert 'مبيعات أكتوبر' in text

def test_background_wake_notifies_hidden_renderer_without_focus(monkeypatch):
 from voice import background_window,wake
 calls=[]
 controller=SimpleNamespace(open=lambda:calls.append('focus'),window=SimpleNamespace(evaluate_js=lambda js:calls.append(js)))
 monkeypatch.setattr(background_window,'_active',controller)
 monkeypatch.setattr(wake,'wake_preferences',lambda:{'show_on_wake':False})
 background_window.show_on_wake()
 assert len(calls)==1 and 'barq-native-wake' in calls[0]

def test_installer_and_frozen_resources_include_background_speaker():
 root=Path(__file__).resolve().parents[1]
 assert '--setup-personal-assistant' in (root/'scripts/installer.iss').read_text()
 script=(root/'scripts/build_windows.ps1').read_text()
 assert 'models/speaker;models/speaker' in script and "'sherpa_onnx'" in script

@pytest.mark.asyncio
async def test_routine_supports_volume_through_existing_permission_gate(monkeypatch):
 import computer_control.api as api
 monkeypatch.setattr(api,'load_policy',lambda:Policy(enabled=True))
 p.configure(routines={'وضع اللعب':['ظبط الصوت على 30 في المية','افتح Steam']})
 calls=[]
 async def launch(tool,args,chat):calls.append((tool,args));return {'status':'ok' if tool=='control_windows_setting' else 'opened'}
 result=await p.execute('وضع اللعب',policy=Policy(enabled=True),launcher=launch)
 assert result['status']=='ok' and calls[0][0]=='control_windows_setting' and calls[0][1]['percent']==30

@pytest.mark.asyncio
async def test_emergency_generation_stops_subsequent_routine_steps(monkeypatch):
 import computer_control.api as api
 from services import assistant_runtime as runtime
 monkeypatch.setattr(api,'load_policy',lambda:Policy(enabled=True))
 monkeypatch.setattr(runtime,'generation',5)
 p.configure(routines={'جهزني للشغل':['افتح Excel','افتح Word']})
 calls=[]
 async def launch(*args):calls.append(args);runtime.generation+=1;return {'status':'opened'}
 result=await p.execute('جهزني للشغل',policy=Policy(enabled=True),launcher=launch)
 assert result['status']=='stopped' and len(calls)==1

def test_notifications_require_explicit_ack_and_reject_cross_origin():
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from services.personal_api import router
 app=FastAPI();app.include_router(router)
 p.push('done','unique')
 with TestClient(app) as client:
  first=client.get('/v1/personal/notifications').json()['items']
  assert client.get('/v1/personal/notifications').json()['items']==first
  assert client.post('/v1/personal/notifications/ack',json={'ids':[first[0]['id']]},headers={'Origin':'https://evil.test'}).status_code==403
  assert client.post('/v1/personal/notifications/ack',json={'ids':[first[0]['id']]}).status_code==200
  assert client.get('/v1/personal/notifications').json()['items']==[]

@pytest.mark.asyncio
async def test_selection_translation_uses_real_engine_response_and_local_preference(monkeypatch):
 from services import windows_media
 monkeypatch.setattr(windows_media,'selected_text',lambda _: 'Hello')
 class Engine:
  local_only=True
  async def run(self,messages,**kwargs):
   assert kwargs['model']=='local-only' and messages[-1]['content']=='Hello'
   return {'content':'أهلًا'}
 result=await p.execute('ترجم المحدد',policy=Policy(enabled=True),engine=Engine())
 assert result['message']=='أهلًا'

@pytest.mark.asyncio
@pytest.mark.parametrize('changed',[False,True])
async def test_undo_restores_only_unchanged_barq_edit(tmp_path,monkeypatch,changed):
 from workspace import manager as work
 monkeypatch.setattr(work,'state_file',lambda name:tmp_path/name)
 target=tmp_path/'report.txt';target.write_text('before')
 proposed=work.propose(str(tmp_path),'report.txt','after');work.apply(proposed['approval_id'],True)
 if changed:target.write_text('external edit')
 result=await p.execute('رجع آخر تغيير',policy=Policy(enabled=True,direct_commands=True,allowed_folders=[str(tmp_path)]))
 assert target.read_text()==('external edit' if changed else 'before')
 assert result['status']==('unavailable' if changed else 'ok')
