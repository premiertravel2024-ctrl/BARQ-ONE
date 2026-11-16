"""A failed JSON planner can still prepare a *reviewable*, unapproved code edit."""
import pytest
from agent import orchestrator
from router.engine import AllModelsFailed

@pytest.mark.asyncio
async def test_json_failure_generates_preview_only(tmp_path):
    project=tmp_path/'barq-app'
    project.mkdir()
    (project/'main.py').write_text('print("starter")\n',encoding='utf-8')
    calls=[]
    class FakeEngine:
        async def run(self,messages,**kwargs):
            calls.append(kwargs)
            if 'Generate implementation code, NOT JSON' not in messages[0]['content']:
                raise AllModelsFailed(['invalid JSON'])
            return {'content':'### FILE: barq-app/main.py\n```python\nprint("real feature")\n```', 'model':'ollama/fake'}
    result=await orchestrator.plan(FakeEngine(),str(tmp_path),[{'role':'user','content':'اعمل برنامج كامل'}],project_hint='barq-app',task_goal='اعمل برنامج كامل')
    assert result['plan']['steps'][0]['tool']=='workspace_edit'
    assert (project/'main.py').read_text()=='print("starter")\n'
    assert len(calls)==2
    assert calls[1]['response_validator'] if 'response_validator' in calls[1] else True
    orchestrator.PENDING.pop(result['plan_id'])

@pytest.mark.asyncio
async def test_fallback_rejects_other_file_and_truncated(tmp_path):
    project=tmp_path/'barq-app'; project.mkdir()
    (project/'main.py').write_text('print(1)\n')
    class Fake:
        def __init__(self,body):self.body=body
        async def run(self,messages,**kwargs):
            if 'Generate implementation code, NOT JSON' not in messages[0]['content']:raise AllModelsFailed(['invalid plan'])
            return {'content':self.body,'model':'ollama/fake'}
    for body in ['### FILE: ../evil.py\n```python\nprint(4)\n```',
                 '### FILE: barq-app/main.py\n```python\nprint(4)']:
        with pytest.raises(AllModelsFailed):
            await orchestrator.plan(Fake(body),str(tmp_path),[{'role':'user','content':'برمج'}],project_hint='barq-app',task_goal='برمج')
    assert (project/'main.py').read_text()=='print(1)\n'
