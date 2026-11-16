"""Real files, approvals and pytest through the main-chat executor; models are offline fakes."""
import json
import sys
from unittest.mock import AsyncMock
import pytest
from brain.coordinator import Brain
from brain.state import TaskStore
from agent import orchestrator as agent
from workspace import manager
from tests.test_v218_recovery import Plans,step


@pytest.mark.asyncio
async def test_create_edit_test_project_to_verified_completion(tmp_path):
    source='def tracks(text):\n    return [line for line in text.splitlines() if line and not line.startswith("#")]\n'
    test='from main import tracks\n\ndef test_playlist():\n    assert tracks("#EXTM3U\\na.mp3\\n\\nb.mp3") == ["a.mp3", "b.mp3"]\n'
    model=Plans(step('workspace_edit',path='barq-app/main.py',content=source),
                step('workspace_edit',path='barq-app/test_playlist.py',content=test),
                step('run_tests',project='barq-app'),{'steps':[],'answer':'نفّذت الوظيفة والاختبار نجح.'})
    brain=Brain(model,TaskStore(tmp_path/'brain.db'))
    prepared=await brain.prepare(str(tmp_path),[{'role':'user','content':'ابني تطبيق موسيقى'}],conversation_id='main-chat')
    assert prepared['plan']['steps'][0]['tool']=='project_bootstrap'
    assert not (tmp_path/'barq-app').exists()
    with pytest.raises(ValueError,match='Approval'):
        await brain.execute(prepared['plan_id'],False,'main-chat')
    created=await brain.execute(prepared['plan_id'],True,'main-chat')
    assert (tmp_path/'barq-app/main.py').exists()
    plan=created['next_plan']
    for path in ('barq-app/main.py','barq-app/test_playlist.py'):
        preview=await brain.execute(plan['plan_id'],True,'main-chat')
        approval=preview['pending_edit']['approval_id']
        brain.check_save(approval,'main-chat')
        receipt=manager.apply(approval,True)
        brain.saved(approval,receipt)
        result=await brain.resume(approval,receipt['backup_id'],True,'main-chat')
        # A lost HTTP response may repeat resume, but never consumes/replans twice.
        assert await brain.resume(approval,receipt['backup_id'],True,'main-chat')==result
        plan=result['next_plan']
    finished=await brain.execute(plan['plan_id'],True,'main-chat')
    assert finished['task_status']=='completed'
    result=json.loads(finished['results'][0]['result'])
    assert result['exit_code']==0 and '1 passed' in result['stdout']
    assert len(brain.store.get(prepared['task_id'])['saved_paths'])==2
    with pytest.raises(ValueError):
        await brain.execute(plan['plan_id'],True,'main-chat')


@pytest.mark.asyncio
async def test_windows_build_is_offered_but_not_faked_on_other_systems(tmp_path):
    if sys.platform=='win32':pytest.skip('This case verifies the non-Windows blocker')
    (tmp_path/'main.py').write_text('print("app")')
    brain=Brain(Plans(step('project_build',profile='python',entry='main.py',name='Music')),
                TaskStore(tmp_path/'brain.db'))
    prepared=await brain.prepare(str(tmp_path),[{'role':'user','content':'ابني EXE من المشروع'}],conversation_id='main-chat',inspection=False)
    result=await brain.execute(prepared['plan_id'],True,'main-chat')
    assert result['task_status']=='blocked'
    assert not result['results'][0]['success']
    assert 'Windows' in result['results'][0]['error']
    assert not (tmp_path/'dist').exists()


@pytest.mark.parametrize('tool', ['project_bootstrap','project_build','workspace_edit','run_tests'])
@pytest.mark.asyncio
async def test_every_mutating_or_executing_action_requires_approval(tmp_path,tool):
    token='a'+tool
    agent.PENDING[token]={'workspace':str(tmp_path),'plan':{'steps':[{'tool':tool,'args':{}}]},'expires':99999999999}
    try:
        with pytest.raises(ValueError,match='Approval'):
            await agent.execute(Plans(),token,False)
        assert token in agent.PENDING
    finally:agent.PENDING.pop(token,None)


def test_build_of_existing_project_does_not_bootstrap_a_new_one():
    from agent.task_intent import classify_task
    assert classify_task('ابني EXE من المشروع')['new_project'] is False
    assert classify_task('كمل المشروع',['ابنيلي تطبيق موسيقى'])['contextual']
