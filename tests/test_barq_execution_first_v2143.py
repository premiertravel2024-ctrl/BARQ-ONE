"""Execution-first routing, safe local bootstrap, and no unapproved writes."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agent.task_intent import classify_task
from coding.bootstrap import scaffold
from brain.coordinator import Brain
from brain.state import TaskStore
from agent import orchestrator as agent

@pytest.mark.parametrize('query', [
    'ابنيلي برنامج سطح مكتب',
    'اعمللي تطبيق تسجيل دخول',
    'صمملي موقع ويب',
    'برمج برنامج جديد',
])
def test_create_app_is_action_not_explanation(query):
    result=classify_task(query)
    assert result and result['kind']=='coding' and result['new_project'] is True


def test_followup_keeps_user_goal():
    result=classify_task('انا عاوزك تعمله',['ابنيلي برنامج سطح مكتب'])
    assert result and result['kind']=='coding' and result['contextual']


@pytest.mark.parametrize('query', ['اكتبلي كود Python','اشرح برنامج Python','ممكن تشرحلي المشروع؟'])
def test_information_requests_do_not_mutate_workspace(query):
    assert classify_task(query) is None


def test_bootstrap_starter_is_safe_and_runnable(tmp_path):
    result=scaffold(str(tmp_path),'barq-test','desktop_python')
    assert result['created'] and result['runnable_starter_only']
    app=tmp_path/'barq-test'/'main.py'
    compile(app.read_text('utf-8'),str(app),'exec')
    assert (tmp_path/'barq-test'/'README.md').exists()
    with pytest.raises(ValueError): scaffold(str(tmp_path),'barq-test','desktop_python')
    with pytest.raises(ValueError): scaffold(str(tmp_path),'../escape','desktop_python')
    with pytest.raises(ValueError): scaffold(str(tmp_path),'valid-name','unknown')


def test_bootstrap_web_is_viewable_without_dependencies(tmp_path):
    result=scaffold(str(tmp_path),'webapp','web_static')
    assert result['created']
    html=(tmp_path/'webapp'/'index.html').read_text('utf-8')
    assert '<!doctype html>' in html and 'addEventListener' in html


@pytest.mark.asyncio
async def test_prepare_new_app_never_invokes_model_or_writes_without_approval(tmp_path):
    mocked=SimpleNamespace(run=AsyncMock(side_effect=AssertionError('Model should not be needed for local starter')))
    brain=Brain(mocked,TaskStore(tmp_path/'state.sqlite3'))
    root=tmp_path/'workspace';root.mkdir()
    prepared=await brain.prepare(str(root),[{'role':'user','content':'ابنيلي برنامج سطح مكتب'}],conversation_id='app-task')
    assert prepared['plan']['steps'][0]['tool']=='project_bootstrap'
    assert prepared['task_status']=='awaiting_approval'
    assert not (root/'barq-app').exists()
    mocked.run.assert_not_called()
    with pytest.raises(ValueError):
        await agent.execute(mocked, prepared['plan_id'], confirmed=False)
    assert not (root/'barq-app').exists()
    # Explicit user approval runs the starter creation but must not claim full app completion.
    # Mock further model generation to avoid external dependencies and check executed output.
    mocked.run=AsyncMock(return_value={'content':'{"reason":"starter created","steps":[],"answer":"starter only"}','model':'mock/free'})
    outcome=await brain.execute(prepared['plan_id'], confirmed=True, conversation_id='app-task')
    assert (root/'barq-app'/'main.py').exists()
    assert outcome['results'][0]['tool']=='project_bootstrap'
    assert outcome['results'][0]['success'] is True
