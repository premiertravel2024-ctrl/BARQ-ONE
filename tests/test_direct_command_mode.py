"""Direct-mode behavior: general tools, launcher, Office and persisted settings."""
from pathlib import Path
from types import SimpleNamespace as NS
import json
import pytest
from computer_control.safety.policy import Policy,Mode,Decision
from computer_control.tools.schema import validate
from computer_control.tools.office import script_for,perform
from launcher.routines import office_request
from launcher.resolver import Resolver
from launcher.indexes import Index

@pytest.mark.parametrize('tool,args',[
 ('open_app',{'name':'C:/Apps/Editor.exe'}),
 ('open_file',{'path':'/workspace/report.txt'}),
 ('open_folder',{'path':'/workspace/files'}),
 ('open_url',{'url':'https://example.com'}),
 ('focus_window',{'title':'Editor'}),
 ('close_window',{'title':'Editor'}),
 ('close_app',{'name':'notepad.exe'}),
 ('click',{'x':20,'y':30}),
 ('hotkey',{'keys':['ctrl','s']}),
 ('type_text',{'text':'hello'}),
 ('paste',{'text':'مرحبا'}),
 ('write_file',{'path':'/workspace/new.txt','text':'new'}),
 ('copy',{'src':'/workspace/a.txt','dst':'/workspace/b.txt'}),
 ('move',{'src':'/workspace/a.txt','dst':'/workspace/b.txt'}),
 ('delete',{'path':'/workspace/a.txt'}),
 ('run_command',{'cmd':'python --version'}),
 ('set_volume',{'percent':30}),
 ('set_brightness',{'percent':40}),
 ('office_document',{'app':'excel','action':'new'}),
])
def test_explicit_direct_mode_removes_per_step_prompt(tool,args):
 p=Policy(enabled=True,mode=Mode.ASK,direct_commands=True)
 assert p.evaluate(tool,args)[1]==Decision.ALLOW

@pytest.mark.parametrize('tool,args',[
 ('run_command',{'cmd':'format C:'}),
 ('read_file',{'path':'/home/me/.ssh/id_rsa'}),
 ('delete',{'path':'/workspace/a.txt','permanent':True}),
 ('office_document',{'app':'excel','action':'new','cmd':'malicious'}),
 ('set_volume',{'percent':200}),
])
def test_direct_mode_keeps_explicit_blocks(tool,args):
 assert Policy(enabled=True,direct_commands=True).evaluate(tool,args)[1]==Decision.BLOCK
 assert Policy(enabled=True,direct_commands=True,mode=Mode.OBSERVE).evaluate('open_app',{'name':'Excel'})[1]==Decision.BLOCK

@pytest.mark.parametrize('text,app,action',[
 ('افتح شيت اكسيل جديد','excel','new'),
 ('افتحي شيت إكسيل جديد','excel','new'),
 ('افتحلي شيت اكسيل','excel','new'),
 ('اعملي شيت جديد','excel','new'),
 ('افتح اكسيل','excel','open'),
 ('افتح ملف وورد جديد','word','new'),
 ('create a new Excel workbook','excel','new'),
 ('open a blank PowerPoint presentation','powerpoint','new'),
])
def test_office_is_creation_not_existing_filename_search(text,app,action):
 assert office_request(text)=={'app':app,'action':action}

@pytest.mark.parametrize('text',['افتح تقرير.xlsx','افتح شيت اكسيل جديد واكتب المبيعات','ازاي افتح شيت اكسيل جديد','متفتحش اكسيل','افتح اكسيل ملف احمد'])
def test_office_never_discards_extra_requirements(text):assert office_request(text) is None


def test_new_sheet_is_one_candidate_without_scanning_excel_duplicates(tmp_path):
 def forbidden():raise AssertionError('No installed-app/file index lookup for a new document')
 resolver=Resolver(Index(tmp_path/'index.sqlite',[]),Policy(enabled=True,direct_commands=True,mode=Mode.ASK),app_source=forbidden)
 resolver.index.search=lambda *args:forbidden()
 outcome=resolver.resolve('افتح شيت اكسيل جديد')
 assert outcome.decision=='auto' and len(outcome.candidates)==1
 entry=resolver.candidate(outcome.candidates[0]['id'])
 assert entry.tool=='office_document' and entry.args=={'app':'excel','action':'new'}
 assert resolver.resolve('افتح كروم وبعدين اكتب عنوان الموقع') is None


def test_general_launcher_direct_mode_and_stop_remain_active(tmp_path):
 from computer_control.executor.manager import Manager
 from computer_control.adapters.base import FakeAdapter
 from computer_control.audit.journal import Audit
 adapter=FakeAdapter();manager=Manager(adapter,None,Policy(enabled=True,mode=Mode.ASK,direct_commands=True),Audit(tmp_path/'audit.jsonl'))
 result=manager.launch_direct('open_app',{'name':'SomeEditor.exe'},source='voice')
 assert result['status']=='opened' and adapter.calls==[('open_app',{'name':'SomeEditor.exe'})]
 manager.policy.enabled=False
 with pytest.raises(RuntimeError):manager.launch_direct('open_app',{'name':'SomeEditor.exe'},source='voice')
 manager.policy.enabled=True;manager.tools.cancel()
 with pytest.raises(RuntimeError):manager.launch_direct('open_app',{'name':'SomeEditor.exe'},source='voice')


def test_direct_mode_persists_and_can_be_revoked(tmp_path,monkeypatch):
 from computer_control import api
 settings=tmp_path/'settings.json'
 monkeypatch.setattr(api,'state_file',lambda name:settings)
 settings.write_text(json.dumps({'enabled':True,'mode':'ask-always'}))
 assert api.load_policy().direct_commands is True
 settings.write_text(json.dumps({'enabled':True,'direct_commands':False}))
 assert api.load_policy().direct_commands is False
 settings.write_text(json.dumps({'enabled':False,'direct_commands':True}))
 assert api.load_policy().enabled is False


def test_office_executes_fixed_com_script_and_requires_evidence(monkeypatch):
 import computer_control.tools.office as office
 monkeypatch.setattr(office.sys,'platform','win32')
 calls=[]
 def runner(argv,**kwargs):
  calls.append((argv,kwargs))
  return NS(returncode=0,stdout='{"ok":true,"verified":true,"document_name":"Book1"}')
 result=perform({'app':'excel','action':'new'},runner=runner)
 assert result['verified'] and result['saved'] is False
 assert calls[0][1]['shell'] is False
 assert 'Workbooks.Add(-4167)' in calls[0][0][-1]
 assert 'SaveAs' not in calls[0][0][-1]
 with pytest.raises(RuntimeError):perform({'app':'excel','action':'new'},runner=lambda *a,**kw:NS(returncode=0,stdout='{}'))
 with pytest.raises(RuntimeError):perform({'app':'excel','action':'new'},runner=lambda *a,**kw:NS(returncode=1,stdout=''))
 for args in ({'app':'evil','action':'new'},{'app':'excel','action':'run'},{'app':'excel','action':'new','path':'x'}):
  with pytest.raises(ValueError):validate('office_document',args)


def test_office_typed_and_voice_use_same_real_launcher(monkeypatch,tmp_path):
 import asyncio
 from voice.brain_bridge import BARQVoiceBrain,action_route
 from voice.command_guard import VoiceCommandGate
 calls=[]
 async def dispatch(name,args,cid):
  calls.append((name,args));return {'status':'opened','message':'فتحت شيت جديد.'}
 gate=VoiceCommandGate();gate.record('افتحي شيت اكسيل جديد')
 result=asyncio.run(BARQVoiceBrain(dispatcher=dispatch).ask(gate,computer_enabled=True))
 assert result['status']=='opened'
 assert calls==[('open_on_computer',{'request':'افتحي شيت اكسيل جديد'})]


@pytest.mark.parametrize('text',['افتح برنامج OBS','افتح Discord','افتح ملف فاتورة.pdf','اقفل كروم','انسخ ملف التقرير للتنزيلات'])
def test_generic_desktop_commands_do_not_become_coding_projects(text):
    from agent.task_intent import classify_task
    result=classify_task(text)
    assert result and result['kind']=='computer'
