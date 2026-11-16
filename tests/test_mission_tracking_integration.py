import hashlib
import pytest
from mission.tracking import start, load_project, mark_saved
from mission.state import report


def test_scaffold_is_not_completion_and_saved_edit_is_not_verified(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    project=workspace/'barq-app';project.mkdir()
    (project/'main.py').write_text('print(1)\n',encoding='utf-8')
    (project/'README.md').write_text('starter',encoding='utf-8')
    start(str(workspace),'barq-app','desktop_python','ابني برنامج',['main.py','README.md'])
    mission=load_project(str(workspace),'barq-app')
    assert mission and not report(mission)['complete']
    new='print(2)\n'; (project/'main.py').write_text(new,encoding='utf-8')
    digest=hashlib.sha256(new.encode()).hexdigest()
    with pytest.raises(ValueError):
        mark_saved(str(workspace),'barq-app','barq-app/main.py','0'*64)
    mark_saved(str(workspace),'barq-app','barq-app/main.py',digest)
    mission=load_project(str(workspace),'barq-app')
    assert mission['manifest'][0]['status']=='written'
    assert report(mission)['complete'] is False


def test_reject_escape(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    project=workspace/'app';project.mkdir()
    (project/'main.py').write_text('x=1',encoding='utf-8')
    start(str(workspace),'app','desktop_python','test',['main.py'])
    with pytest.raises(ValueError):
        mark_saved(str(workspace),'app','../outside.py',hashlib.sha256(b'').hexdigest())

@pytest.mark.asyncio
async def test_saved_mission_source_proposes_local_check_without_model_call(tmp_path, monkeypatch):
    import json
    from agent import orchestrator
    from workspace import manager
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path/'state'))
    root=tmp_path/'workspace'; root.mkdir()
    project=root/'app'; project.mkdir()
    (project/'main.py').write_text('print(1)\n', encoding='utf-8')
    start(str(root),'app','desktop_python','ابني تطبيق',['main.py'])
    preview=manager.propose(str(root),'app/main.py','print(2)\n')
    approval=preview['approval_id']
    digest=hashlib.sha256(b'print(2)\n').hexdigest()
    orchestrator.PENDING_EDITS[approval]={
        'workspace':str(root),'model':'auto',
        'messages':[{'role':'user','content':'ابني تطبيق'}],
        'round':1,'rea_requested':False,'task_goal':'ابني تطبيق',
        'project_hint':'app','path':'app/main.py',
        'expires':orchestrator.time.monotonic()+600,'content_sha256':digest}
    saved=manager.apply(approval,True)
    class NoLLM:
        async def run(self,*args,**kwargs):
            raise AssertionError('Static check proposal must not call any model')
    answer=await orchestrator.resume_after_saved_edit(NoLLM(),approval,saved['backup_id'],True)
    assert answer['next_plan']['plan']['steps']==[{'tool':'code_check','args':{'path':'app/main.py'}}]
    assert (project/'main.py').read_text()=='print(2)\n'
    assert load_project(str(root),'app')['manifest'][0]['status']=='written'
