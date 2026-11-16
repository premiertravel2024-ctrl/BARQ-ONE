"""No real models or network: a complete approved multi-file mission cycle."""
import json
from pathlib import Path
import pytest

from agent import orchestrator as agent
from mission.tracking import load_project, project_for_goal
from mission.engine import project_name, mission_progress
from workspace import manager


class FakeSourceEngine:
    # The production gate is tested without any actual provider or network.
    network=object()
    limiter=object()

    def __init__(self):self.calls=[]

    async def run(self,messages,**kwargs):
        self.calls.append((messages,kwargs))
        prompt=messages[0]['content']
        assert kwargs['task_hint']=='coding'
        assert kwargs['use_cache'] is False
        path=prompt.split('### FILE: ',1)[1].split('\n',1)[0]
        if path.endswith('main.py'):
            code='from storage import get_label\n\ndef main():\n    print(get_label())\n\nif __name__ == "__main__":\n    main()\n'
        elif path.endswith('storage.py'):
            code='def get_label():\n    return "ready"\n'
        elif path.endswith('test_app.py'):
            code='from storage import get_label\n\ndef test_label():\n    assert get_label() == "ready"\n'
        elif path.endswith('.md'):
            code='# TOFU Desktop Buddy\n\nA prototype, not a verified Windows executable.\n'
        else:raise AssertionError('Unknown requested source file '+path)
        return {'model':'ollama/fake','content':f'### FILE: {path}\n```\n{code}```\n'}


@pytest.mark.asyncio
async def test_full_multifile_approved_flow_without_replanning(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    goal='يا برق اعملي برنامج Windows اسمه TOFU Desktop Buddy'
    messages=[{'role':'user','content':goal}]
    engine=FakeSourceEngine()
    prepared=await agent.prepare_task(engine,str(workspace),messages,task_intent={
        'kind':'coding','goal':goal,'new_project':True})
    assert prepared['plan']['steps'][0]['tool']=='project_bootstrap'
    assert not list(workspace.iterdir())  # no unauthorized initial scaffold
    scaffold=await agent.execute(engine,prepared['plan_id'],confirmed=True,defer_replan=True)
    assert scaffold['deferred']
    project='tofu-desktop-buddy'
    assert (workspace/project/'main.py').exists()
    assert project_for_goal(str(workspace),goal)==project
    manifest=load_project(str(workspace),project)['manifest']
    assert [x['path'] for x in manifest]==[
        f'{project}/storage.py', f'{project}/main.py', f'{project}/test_app.py', f'{project}/README.md']
    token=scaffold['retry_id']
    for filename in ('storage.py','main.py','test_app.py','README.md'):
        proposal=await agent.retry_plan(engine,token)
        ready=proposal['next_plan'];step=ready['plan']['steps'][0]
        assert step['tool']=='workspace_edit'
        assert step['args']['path']==f'{project}/{filename}'
        if filename=='storage.py':
            assert not (workspace/project/'storage.py').exists()
        preview=await agent.execute(engine,ready['plan_id'],confirmed=True)
        edit=preview['pending_edit']
        assert edit['path']==f'{project}/{filename}'
        # Merely previewing cannot commit an edit.
        if filename=='storage.py':assert not (workspace/project/'storage.py').exists()
        saved=manager.apply(edit['approval_id'],confirmed=True)
        result=await agent.resume_after_saved_edit(
            engine,edit['approval_id'],saved['backup_id'],confirmed=True,defer_replan=True)
        assert result.get('deferred') is True
        token=result['retry_id']
        assert next(x for x in load_project(str(workspace),project)['manifest']
                    if x['path'].endswith(filename))['status']=='written'
    # No generator calls for deterministic local syntax checks.
    calls=len(engine.calls)
    verify=await agent.retry_plan(engine,token)
    assert verify['next_plan']['plan']['steps'][0]['tool']=='code_check'
    assert len(engine.calls)==calls==4
    assert mission_progress(str(workspace),project)['calls_used']==4
    assert all(row['status']=='written' for row in load_project(str(workspace),project)['manifest'])
    assert not any(row['status']=='verified' for row in load_project(str(workspace),project)['manifest'])
    # The mission must continue beyond syntax without another user request.
    current=verify['next_plan']
    for _ in range(3):
        assert current['plan']['steps'][0]['tool']=='code_check'
        outcome=await agent.execute(engine,current['plan_id'],confirmed=True,defer_replan=True)
        current=(await agent.retry_plan(engine,outcome['retry_id']))['next_plan']
    assert current['plan']['steps']==[{'tool':'run_tests','args':{'project':project}}]
    tested=await agent.execute(engine,current['plan_id'],confirmed=True,defer_replan=True)
    assert tested['results'][0]['success']
    assert '1 passed' in tested['results'][0]['result']
    build=(await agent.retry_plan(engine,tested['retry_id']))['next_plan']
    assert build['plan']['steps']==[{'tool':'project_build','args':{
        'project':project,'profile':'python','entry':'main.py','name':project}}]
    assert len(engine.calls)==4  # tests and build preparation are deterministic
    agent.PENDING.pop(build['plan_id'],None)



def test_explicit_project_name_is_bounded():
    assert project_name('عاوز برنامج اسمه TOFU Desktop Buddy، مستوحى من الفيديو')=='tofu-desktop-buddy'
    assert project_name('ابني تطبيق')=='barq-app'

@pytest.mark.asyncio
async def test_bad_model_cannot_write_outside_project_or_trigger_json_replans(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    root=tmp_path/'workspace';root.mkdir()
    goal='ابني برنامج اسمه Safe App'
    class Broken(FakeSourceEngine):
        async def run(self,messages,**kwargs):
            self.calls.append((messages,kwargs))
            return {'model':'ollama/fake','content':'### FILE: ../outside.py\n```python\nprint(1)\n```'}
    engine=Broken()
    init=await agent.prepare_task(engine,str(root),[{'role':'user','content':goal}],task_intent={
        'kind':'coding','goal':goal,'new_project':True})
    approved=await agent.execute(engine,init['plan_id'],confirmed=True,defer_replan=True)
    continued=await agent.retry_plan(engine,approved['retry_id'])
    assert continued['paused'] is True
    assert continued['next_plan'] is None
    assert not (tmp_path/'outside.py').exists()
    assert len(engine.calls)==2
    saved=load_project(str(root),'safe-app')
    assert saved['calls_used']==2
    assert saved['manifest'][0]['status']=='pending'
    assert saved['manifest'][0]['attempts']==2
