import copy,hashlib,json,sys
from pathlib import Path
import pytest
from agent import orchestrator as agent
from mission.blueprint import validate_blueprint,approve_blueprint,requirement_progress
from mission.tracking import start,load_project
from mission.runtime import verify_runtime,run_process
from mission.validation import fingerprint,record_validation
from workspace import manager

BLUEPRINT={'summary':'Calculator with a separate domain module and observable tests',
 'files':[{'path':'domain.py','purpose':'Validate and sum numeric input','depends_on':[]},
          {'path':'main.py','purpose':'Entry point and noninteractive startup verification','depends_on':['domain.py']},
          {'path':'tests/test_domain.py','purpose':'Check valid and invalid input','depends_on':['domain.py']},
          {'path':'README.md','purpose':'Actual launch instructions and limitations','depends_on':[]}],
 'requirements':[{'id':'R1','title':'Sum numbers safely','acceptance':'Return the sum and reject nonnumeric inputs',
                  'files':['domain.py','main.py'],'tests':['tests/test_domain.py::test_total','tests/test_domain.py::test_invalid']} ]}

SOURCES={'domain.py':'def total(values):\n    if not all(isinstance(v, (int, float)) for v in values):\n        raise ValueError("Numbers required")\n    return sum(values)\n',
 'main.py':'import sys\nfrom domain import total\n\ndef main():\n    if "--barq-smoke-test" in sys.argv:\n        assert total([2, 3]) == 5\n        print("BARQ_SMOKE_OK")\n    else:\n        print(total([2, 3]))\n\nif __name__ == "__main__":\n    main()\n',
 'tests/test_domain.py':'import pytest\nfrom domain import total\n\ndef test_total():\n    assert total([2,3]) == 5\n    assert total([]) == 0\n\ndef test_invalid():\n    with pytest.raises(ValueError):\n        total(["bad"])\n',
 'README.md':'# Calculator\n\nRun python main.py. Run python -m pytest. GUI not implemented in this test fixture.\n'}

class PlannedEngine:
    project_planning=True
    network=object()
    limiter=object()
    def __init__(self):self.calls=[]
    async def run(self,messages,**kwargs):
        prompt=messages[0]['content'];self.calls.append(prompt)
        if prompt.startswith('Design a small'):
            content=json.dumps(BLUEPRINT)
        else:
            target=prompt.split('### FILE: ',1)[1].split('\n')[0]
            content='### FILE: '+target+'\n```\n'+SOURCES[target.split('/',1)[1]]+'```'
        kwargs['response_validator'](content)
        return {'model':'controlled/test','content':content}

@pytest.mark.asyncio
async def test_full_planned_mission_uses_real_tests_startup_and_approvals(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';root.mkdir();engine=PlannedEngine()
    goal='Build a calculator desktop app'
    current=await agent.prepare_task(engine,str(root),[{'role':'user','content':goal}],task_intent={'kind':'coding','goal':goal,'new_project':True})
    tools=[]
    for _ in range(30):
        steps=current['plan']['steps']
        if not steps:break
        tools.append(steps[0]['tool'])
        result=await agent.execute(engine,current['plan_id'],True,defer_replan=True)
        if result.get('pending_edit'):
            edit=result['pending_edit'];path=root/edit['path']
            before=path.read_text() if path.exists() else None
            assert before!=SOURCES.get(edit['path'].split('/',1)[1])
            saved=manager.apply(edit['approval_id'],True)
            result=await agent.resume_after_saved_edit(engine,edit['approval_id'],saved['backup_id'],True,defer_replan=True)
        if result.get('deferred'):
            continued=await agent.retry_plan(engine,result['retry_id'])
            if not continued.get('next_plan'):
                assert not continued.get('paused'),continued
                break
            current=continued['next_plan']
        else:
            assert not result.get('blocked'),result
            break
    else:raise AssertionError('Mission did not terminate within its expected steps')
    assert tools[:2]==['project_bootstrap','project_plan']
    assert 'project_directory' in tools and tools[-3:]==['run_tests','project_acceptance','project_smoke']
    m=load_project(str(root),'barq-app')
    assert [p['path'] for p in m['manifest']]==['barq-app/'+p for p in SOURCES]
    assert requirement_progress(str(root),'barq-app',m)[0]['status']=='tests_passed'
    assert all(row['success'] for row in m['validation'].values())
    assert len(engine.calls)==5 # One architecture call and four source calls; checks are local.
    (root/'barq-app/domain.py').write_text('def total(values):\n return -1\n')
    assert requirement_progress(str(root),'barq-app',m)[0]['status']!='tests_passed'

@pytest.mark.parametrize('mutate',[
    lambda p:p['files'][0].update(path='../outside.py'),
    lambda p:p['files'][0].update(depends_on=['main.py']),
    lambda p:p['requirements'][0].update(tests=['../test_x.py::test_x']),
    lambda p:p['requirements'][0].update(tests=['tests/test_domain.py::-k']),
    lambda p:p['requirements'][0].update(files=['ghost.py']),
    lambda p:p['files'].append(p['files'][0]),
])
def test_plan_rejects_unsafe_or_inconsistent_contracts(mutate):
    value=copy.deepcopy(BLUEPRINT);mutate(value)
    with pytest.raises(ValueError):validate_blueprint(value,'desktop_python')

@pytest.mark.asyncio
async def test_runtime_requires_approval_and_skips_are_not_passes(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';(root/'app/tests').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build app',['main.py'])
    approve_blueprint(str(root),'app',BLUEPRINT)
    for name,code in SOURCES.items():(root/'app'/name).write_text(code)
    with pytest.raises(ValueError,match='approval'):await verify_runtime(str(root),'app','acceptance')
    (root/'app/tests/test_domain.py').write_text('import pytest\n@pytest.mark.skip\ndef test_total():\n assert False\n@pytest.mark.skip\ndef test_invalid():\n assert False\n')
    result=await verify_runtime(str(root),'app','acceptance',True)
    assert result['exit_code']!=0 and result['checks']['R1']['exit_code']!=0

@pytest.mark.asyncio
async def test_startup_without_verification_marker_fails_and_timeout_stops(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';(root/'app').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build app',['main.py'])
    approve_blueprint(str(root),'app',BLUEPRINT)
    assert not (root/'app/tests').exists() # Approving architecture never creates source directories.
    (root/'app/main.py').write_text('print("started")\n')
    assert (await verify_runtime(str(root),'app','smoke',True))['exit_code']==1
    result=await run_process([sys.executable,'-c','import time; time.sleep(10)'],root,.1)
    assert result['exit_code']==124

def test_small_repairs_are_exact_guarded_changes():
    from coding.targeted import targeted_step
    old=''.join(f'value_{i} = {i}\n' for i in range(20))
    for new in [old.replace('value_7 = 7','value_7 = 70'),old+'tail = True\n',old.replace('value_7 = 7\n','')]:
        step=targeted_step('main.py',old,new)
        assert step['tool']=='code_replace'
        assert old.replace(step['args']['before'],step['args']['after'],1)==new

@pytest.mark.parametrize('text,kind',[('No module named pytest','environment'),('429 quota','quota'),('connection timeout','connection'),('Source context too small','context'),('SyntaxError invalid','code')])
def test_recovery_classifies_evidence(text,kind):
    from mission.recovery import classify_failure
    assert classify_failure(text)['kind']==kind


def test_extensions_preserve_approved_acceptance_and_written_files(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';(root/'app').mkdir(parents=True)
    start(str(root),'app','desktop_python','Build app',['main.py'])
    approve_blueprint(str(root),'app',BLUEPRINT)
    weaker=copy.deepcopy(BLUEPRINT);weaker['requirements'][0]['tests']=weaker['requirements'][0]['tests'][:1]
    with pytest.raises(ValueError,match='preserve approved'):approve_blueprint(str(root),'app',weaker)
    extra=copy.deepcopy(BLUEPRINT);extra['files'].append({'path':'export.py','purpose':'Export calculation history','depends_on':['domain.py']})
    approve_blueprint(str(root),'app',extra)
    assert load_project(str(root),'app')['manifest'][-1]['path']=='app/export.py'


def test_web_validation_reports_manual_verification_without_repair_loop():
    from mission.validation import next_validation
    result=next_validation('/unused','web',{'kind':'web_static','manifest':[],'blueprint':{'summary':'web'}})
    assert result['steps']==[]
    assert 'مش هاعتبره مكتمل' in result['answer']
