"""Completed writes must not wait for the next model plan or repeat on retries."""
import asyncio,json,time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path
import pytest
from brain.coordinator import Brain
from brain.state import TaskStore
from agent import orchestrator as agent
from tests.test_v219_command_intake import actual_engine,controlled_http


@pytest.mark.asyncio
async def test_execute_receipt_precedes_model_and_starter_context_is_focused(tmp_path):
    (tmp_path/'unrelated.py').write_text('unrelated = True')
    engine=SimpleNamespace(run=AsyncMock(side_effect=AssertionError('No model before execution receipt')))
    brain=Brain(engine,TaskStore(tmp_path/'brain.sqlite3'))
    prepared=await brain.prepare(str(tmp_path),[{'role':'user','content':'ابني برنامج للمخازن'}],conversation_id='fast')
    result=await asyncio.wait_for(brain.execute(prepared['plan_id'],True,'fast',defer_replan=True),timeout=1)
    assert result['deferred'] and result['task_status']=='planning_next'
    assert (tmp_path/'barq-app/main.py').is_file()
    engine.run.assert_not_called()
    reads=[json.loads(entry['result']) for entry in result['results'] if entry['tool']=='workspace_read']
    assert any(row['path']=='barq-app/main.py' and 'tkinter' in row['content'] for row in reads)
    token=result['retry_id']
    assert agent.RETRY_PLANS[token]['project_hint']=='barq-app'
    async def next_model(messages,**kwargs):
        system=messages[0]['content']
        assert 'barq-app/main.py' in system and 'unrelated.py' not in system
        return {'model':'test/free','content':json.dumps({'reason':'Implement features','steps':[{'tool':'code_replace','args':{'path':'barq-app/main.py','before':'BARQ App','after':'Inventory'}}],'answer':'Review next step'})}
    engine.run=next_model
    next_step=await brain.retry_plan(token,'fast')
    assert next_step['next_plan']['plan']['steps'][0]['tool']=='code_replace'
    agent.PENDING.pop(next_step['next_plan']['plan_id'],None)
    assert 'BARQ App' in (tmp_path/'barq-app/main.py').read_text()


@pytest.mark.asyncio
async def test_deferred_continuation_recovers_after_restart_without_recreating_project(tmp_path):
    engine=SimpleNamespace(run=AsyncMock(side_effect=RuntimeError('No model needed')))
    store=TaskStore(tmp_path/'brain.sqlite3');brain=Brain(engine,store)
    plan=await brain.prepare(str(tmp_path),[{'role':'user','content':'ابني برنامج حسابات'}],conversation_id='restart')
    done=await brain.execute(plan['plan_id'],True,'restart',defer_replan=True)
    token=done['retry_id'];agent.RETRY_PLANS.pop(token,None)
    restarted=Brain(engine,TaskStore(tmp_path/'brain.sqlite3'))
    assert restarted.state('restart')['status']=='paused'
    assert token in agent.RETRY_PLANS and (tmp_path/'barq-app/main.py').exists()
    with pytest.raises(ValueError):await restarted.execute(plan['plan_id'],True,'restart',defer_replan=True)
    assert len(list(tmp_path.glob('barq-app*')))==1
    restarted.cancel('restart')


def test_approval_frontend_dispatch_does_not_repeat_approved_actions():
    from tests.test_chat_smoke_launcher_regression import run_smoke
    root=Path(__file__).resolve().parents[1]
    result=run_smoke(root/'frontend/tests/approval-flow.ts')
    assert result.returncode==0,result.stdout+'\n'+result.stderr


@pytest.mark.asyncio
async def test_planning_timeouts_reach_a_faster_allowed_provider(actual_engine,monkeypatch):
    import httpx
    from router.config import Provider,Model
    from brain.understanding import parse_understanding
    actual_engine.config.providers.append(Provider(name='openrouter',base_url='https://openrouter.ai/api/v1',api_key_env='OPENROUTER_API_KEY',
        models=[Model(name='openrouter/free',free=True,strengths=['reasoning'],context_window=32000)]))
    calls=[];limits=[]
    async def upstream(request):
        calls.append(request.url.host)
        if request.url.host=='api.groq.com':await asyncio.sleep(10)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"kind":"coding","goal":"Fix button"}'}}]})
    controlled_http(monkeypatch,upstream)
    real_wait=asyncio.wait_for
    async def accelerated(awaitable,timeout):
        limits.append(timeout)
        return await real_wait(awaitable,timeout=min(timeout,.03))
    monkeypatch.setattr('router.engine.asyncio.wait_for',accelerated)
    result=await actual_engine.run([{'role':'user','content':'Review the project'}],use_cache=False,task_hint='reasoning',response_validator=parse_understanding)
    assert calls==['api.groq.com','openrouter.ai']
    assert len(limits)==2 and all(0<limit<=10 for limit in limits)
    assert parse_understanding(result['content'])['kind']=='coding'


@pytest.mark.asyncio
async def test_cloud_planning_has_a_total_budget(actual_engine,monkeypatch):
    import httpx
    from router.config import Provider,Model
    from router.engine import AllModelsFailed
    actual_engine.config.providers[0].models.append(Model(name='openai/gpt-oss-20b',free=True,strengths=['coding'],context_window=32000))
    actual_engine.config.providers.append(Provider(name='openrouter',base_url='https://openrouter.ai/api/v1',api_key_env='OPENROUTER_API_KEY',
        models=[Model(name='openrouter/free',free=True,strengths=['coding'],context_window=32000)]))
    monkeypatch.setenv('BARQ_PLAN_MODEL_SECONDS','2');monkeypatch.setenv('BARQ_PLAN_BUDGET_SECONDS','5')
    async def upstream(request):
        await asyncio.sleep(20)
        return httpx.Response(500)
    controlled_http(monkeypatch,upstream)
    started=time.monotonic()
    with pytest.raises(AllModelsFailed):
        await actual_engine.run([{'role':'user','content':'Plan a project edit'}],use_cache=False,task_hint='coding',response_validator=json.loads)
    assert time.monotonic()-started<8,'One plan must not spend a full timeout on every provider'
