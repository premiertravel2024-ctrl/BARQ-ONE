"""Regression: repeated original build command resumes, never creates barq-app-N."""
import pytest
from agent import orchestrator as agent
from mission.tracking import project_for_goal, load_project
from workspace import manager

class FileModel:
    network=object()
    limiter=object()
    def __init__(self): self.calls=[]
    async def run(self,messages,**kwargs):
        prompt=messages[0]['content'];self.calls.append(prompt)
        target=prompt.split('### FILE: ',1)[1].split('\n',1)[0]
        if target.endswith('storage.py'):
            code='def get_label():\n    return "TOFU"\n'
        elif target.endswith('main.py'):
            code='from storage import get_label\n\ndef main():\n    print(get_label())\n\nif __name__ == "__main__":\n    main()\n'
        else: code='# TOFU Desktop Buddy\n\nNot yet tested or built.\n'
        return {'model':'ollama/fake','content':f'### FILE: {target}\n```\n{code}```'}

@pytest.mark.asyncio
async def test_repeat_new_project_request_resumes_existing_and_exposes_all_files(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    workspace=tmp_path/'workspace';workspace.mkdir();model=FileModel()
    goal='ابني برنامج Windows اسمه TOFU Desktop Buddy'
    messages=[{'role':'user','content':goal}]
    intent={'kind':'coding','new_project':True,'goal':goal}
    start=await agent.prepare_task(model,str(workspace),messages,task_intent=intent)
    first=await agent.execute(model,start['plan_id'],True,defer_replan=True)
    assert first['mission_progress']['files']
    project=project_for_goal(str(workspace),goal)
    assert project=='tofu-desktop-buddy'
    assert len([p for p in workspace.iterdir() if p.is_dir()])==1
    # Exact repeated command goes directly to the next FILE; no second scaffold.
    repeated=await agent.prepare_task(model,str(workspace),messages,task_intent=intent)
    assert repeated['plan']['steps'][0]['tool']=='workspace_edit'
    assert repeated['plan']['steps'][0]['args']['path']==f'{project}/storage.py'
    assert len([p for p in workspace.iterdir() if p.is_dir()])==1
    # Same named app with different phrasing must still resume, never multiply projects.
    reworded='يا برق عاوز برنامج اسمه TOFU Desktop Buddy'
    assert __import__('mission.tracking',fromlist=['project_for_requested_name']).project_for_requested_name(str(workspace),reworded)==project
    preview=await agent.execute(model,repeated['plan_id'],True,defer_replan=True)
    assert preview['pending_edit']['path'].endswith('storage.py')
    assert not (workspace/project/'storage.py').exists()
    saved=manager.apply(preview['pending_edit']['approval_id'],True)
    resumed=await agent.resume_after_saved_edit(model,preview['pending_edit']['approval_id'],saved['backup_id'],True,defer_replan=True)
    assert resumed['mission_progress']['files'][0]['status']=='written'
    result=await agent.retry_plan(model,resumed['retry_id'])
    assert result['next_plan']['plan']['steps'][0]['args']['path']==f'{project}/main.py'
    assert load_project(str(workspace),project)['manifest'][0]['status']=='written'
    assert len([p for p in workspace.iterdir() if p.is_dir()])==1
