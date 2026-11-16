"""Model outages must not erase completed tool evidence or re-run approved actions."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agent import orchestrator as agent
from brain.coordinator import Brain
from brain.state import TaskStore
from router.engine import AllModelsFailed


@pytest.mark.asyncio
async def test_outage_after_approved_step_preserves_evidence_and_retries_plan_only(tmp_path,monkeypatch):
    calls=[]
    tool_runs=[]
    original_listing=agent.listing
    def tracked_listing(root,*args,**kwargs):
        tool_runs.append('list')
        return original_listing(root,*args,**kwargs)
    monkeypatch.setattr(agent,'listing',tracked_listing)
    class FakeModel:
        async def run(self,messages,**kwargs):
            calls.append(messages)
            if len(calls) in (2,3):
                raise AllModelsFailed(['gemini/gemini-flash: Provider temporary error (HTTP 503)',
                                       'groq/gpt-oss: Model did not return a structured plan'])
            if len(calls)==1:
                step={'tool':'workspace_list','args':{}}
            else:
                step={'tool':'project_diagnostics','args':{}}
            return {'model':'free/mock','content':json.dumps({'reason':'inspect','steps':[step],'answer':'الخطوة جاهزة.'})}
    brain=Brain(FakeModel(),TaskStore(tmp_path/'brain.sqlite3'))
    prepared=await brain.prepare(str(tmp_path),[{'role':'user','content':'صلح الملف في المشروع'}],conversation_id='chat-1',inspection=False)
    assert prepared['plan']['steps'][0]['tool']=='workspace_list'
    result=await brain.execute(prepared['plan_id'],True,'chat-1')
    assert result['paused'] is True
    assert result['results'][0]['success'] is True
    assert result['task_status']=='paused'
    retry_id=result['retry_id']
    assert retry_id in agent.RETRY_PLANS
    before_tool_calls=len(tool_runs)
    with pytest.raises(ValueError,match='another conversation'):
        await brain.retry_plan(retry_id,'chat-2')
    again=await brain.retry_plan(retry_id,'chat-1')
    assert again['paused'] and again['retry_id']==retry_id
    assert again['task_status']=='paused'
    assert len(tool_runs)==before_tool_calls+1  # reading project metadata for re-plan is allowed
    continuation=await brain.retry_plan(retry_id,'chat-1')
    assert continuation['next_plan']['plan']['steps'][0]['tool']=='project_diagnostics'
    assert continuation['task_status']=='awaiting_approval'
    assert len(tool_runs)==before_tool_calls+2  # no workspace tool was re-executed
    assert retry_id not in agent.RETRY_PLANS
    assert any(x['tool']=='workspace_list' for x in brain.store.get(prepared['task_id'])['evidence'])
    # Repeated old retries cannot re-run the approved action.
    with pytest.raises(ValueError):
        await brain.retry_plan(retry_id,'chat-1')


@pytest.mark.asyncio
async def test_cancel_revokes_retry_token(tmp_path):
    b=Brain(SimpleNamespace(run=AsyncMock()),TaskStore(tmp_path/'brain.sqlite3'))
    task=b.store.begin('c','coding','ابني برنامج',str(tmp_path),b.runtime_id)
    token='f'*32
    agent.RETRY_PLANS[token]={'workspace':str(tmp_path),'expires':999999999}
    b.store.update(task['id'],status='paused',retry_id=token)
    assert b.cancel('c')['cancelled']
    assert token not in agent.RETRY_PLANS
    assert b.state('c')['status']=='cancelled'


def test_frontend_retries_are_never_authority_to_execute_tools():
    from tests.test_chat_smoke_launcher_regression import run_smoke
    # Actual typed retry, saved-file recovery and API invocation counts are
    # asserted inside the Node fixture, without a browser window.
    result=run_smoke()
    assert result.returncode==0, result.stdout+'\n'+result.stderr


def test_free_model_preface_can_be_recovered_but_tool_contract_stays_enforced():
    clean='''<think>I'll produce one JSON plan.</think>
    ```json
    {"reason":"read before editing","steps":[{"tool":"workspace_read","args":{"path":"app.py"}}],"answer":"هقرأ الملف"}
    ```'''
    parsed=agent.parse_plan(clean,{'workspace_read','code_check'})
    assert parsed['steps'][0]['tool']=='workspace_read'
    with pytest.raises(ValueError,match='unavailable'):
        agent.parse_plan(clean,{'code_check'})
    bad='{"steps":[]}\n{"steps":[{"tool":"code_check","args":{"path":"x.py"}}]}'
    with pytest.raises(ValueError,match='structured plan'):
        agent.parse_plan(bad,{'code_check'})

@pytest.mark.asyncio
async def test_bootstrap_alone_cannot_be_declared_a_finished_application(tmp_path):
    token='e'*32
    agent.RETRY_PLANS[token]={'workspace':str(tmp_path),'messages':[{'role':'user','content':'ابني تطبيق موسيقى'}],
        'model':'auto','round':2,'rea_requested':False,'task_goal':'ابني تطبيق موسيقى',
        'last_tool':'project_bootstrap','expires':__import__('time').monotonic()+60}
    class EmptyPlan:
        async def run(self,messages,**kwargs):
            return {'model':'free/mock','content':'{"reason":"done","steps":[],"answer":"تطبيقك جاهز"}'}
    result=await agent.retry_plan(EmptyPlan(),token)
    assert result['paused'] and 'مش البرنامج' in result['answer']
    assert token in agent.RETRY_PLANS
    agent.RETRY_PLANS.pop(token,None)
