"""Behavioral release regressions. All model calls are deterministic offline fakes."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from agent import orchestrator as agent
from brain.coordinator import Brain
from brain.state import TaskStore
from router.engine import AllModelsFailed
from workspace import manager


class Plans:
    def __init__(self, *values):
        self.values = iter(values)

    async def run(self, messages, **kwargs):
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return {'model': 'free/mock', 'content': json.dumps(value)}


def step(tool, **args):
    return {'reason': 'verified next action', 'steps': [{'tool': tool, 'args': args}], 'answer': 'جاهز'}


def outage():
    return AllModelsFailed(['gemini/free: HTTP 503'])


@pytest.mark.asyncio
async def test_inspection_outage_keeps_retry_and_evidence(tmp_path):
    b = Brain(Plans(step('workspace_list'), outage()), TaskStore(tmp_path/'brain.db'))
    result = await b.prepare(str(tmp_path), [{'role': 'user', 'content': 'صلح الملف في المشروع'}], conversation_id='owner')
    assert result['paused'] and result['retry_id']
    assert result['task_status'] == 'paused'
    assert result['preparation_results'][0]['success']
    assert b.state('owner')['retry_id'] == result['retry_id']


@pytest.mark.asyncio
async def test_initial_provider_outage_can_be_retried(tmp_path):
    b = Brain(Plans(outage(), step('workspace_list')), TaskStore(tmp_path/'brain.db'))
    result = await b.prepare(str(tmp_path), [{'role': 'user', 'content': 'صلح الملف في المشروع'}], conversation_id='owner')
    assert result['paused'] and not result['plan']['steps']
    continued = await b.retry_plan(result['retry_id'], 'owner')
    assert continued['next_plan']['plan']['steps'][0]['tool'] == 'workspace_list'


@pytest.mark.asyncio
async def test_paused_replanning_survives_process_restart(tmp_path):
    path = tmp_path/'brain.db'
    b = Brain(Plans(step('workspace_list'), outage()), TaskStore(path))
    prepared = await b.prepare(str(tmp_path), [{'role': 'user', 'content': 'صلح الملف في المشروع'}], conversation_id='owner', inspection=False)
    result = await b.execute(prepared['plan_id'], True, 'owner')
    token = result['retry_id']
    agent.RETRY_PLANS.pop(token)  # simulate loss of the old process's volatile memory
    restored = Brain(Plans(step('project_diagnostics')), TaskStore(path))
    assert restored.state('owner')['status'] == 'paused'
    with pytest.raises(ValueError, match='conversation'):
        await restored.retry_plan(token, 'intruder')
    continued = await restored.retry_plan(token, 'owner')
    assert continued['next_plan']['plan']['steps'][0]['tool'] == 'project_diagnostics'
    assert len(restored.store.get(prepared['task_id'])['evidence']) == 1


@pytest.mark.asyncio
async def test_empty_conversation_cannot_consume_owned_plan(tmp_path):
    b = Brain(Plans(step('workspace_list')), TaskStore(tmp_path/'brain.db'))
    result = await b.prepare(str(tmp_path), [{'role': 'user', 'content': 'صلح الملف في المشروع'}], conversation_id='owner', inspection=False)
    with pytest.raises(ValueError, match='conversation'):
        await b.execute(result['plan_id'], True, '')
    assert result['plan_id'] in agent.PENDING


@pytest.mark.asyncio
async def test_build_request_is_not_completed_by_successful_inspection(tmp_path):
    b = Brain(Plans(step('workspace_list'), {'steps': [], 'answer': 'البرنامج جاهز'}), TaskStore(tmp_path/'brain.db'))
    prepared = await b.prepare(str(tmp_path), [{'role': 'user', 'content': 'ابني تطبيق موسيقى وطلّع EXE'}], conversation_id='owner', inspection=False)
    result = await b.execute(prepared['plan_id'], True, 'owner')
    assert result['task_status'] == 'blocked'
    assert result['blocked'] and 'جاهز' not in result['answer']


@pytest.mark.asyncio
async def test_saved_file_outage_keeps_file_and_retry(tmp_path):
    b = Brain(Plans(step('workspace_edit', path='app.py', content='print(42)\n'), outage()), TaskStore(tmp_path/'brain.db'))
    prepared = await b.prepare(str(tmp_path), [{'role': 'user', 'content': 'صلح الملف في المشروع'}], conversation_id='owner', inspection=False)
    preview = await b.execute(prepared['plan_id'], True, 'owner')
    token = preview['pending_edit']['approval_id']
    assert not (tmp_path/'app.py').exists()
    with pytest.raises(ValueError):
        manager.apply(token, False)
    saved = manager.apply(token, True)
    b.saved(token, saved)
    result = await b.resume(token, saved['backup_id'], True, 'owner')
    assert result['paused'] and result['task_status'] == 'paused'
    assert (tmp_path/'app.py').read_text() == 'print(42)\n'
    with pytest.raises(ValueError):
        manager.apply(token, True)


@pytest.mark.parametrize('raw', [
    '{"answer":"done"}',
    '{"steps":[],"steps":[{"tool":"workspace_list","args":{}}]}',
    '{"steps":[],"answer":{"claim":"done"}}',
    '{"steps":[{"tool":"workspace_read","args":{"path":"app.py","path":"other.py"}}]}',
])
def test_ambiguous_or_incomplete_plan_is_rejected(raw):
    with pytest.raises(ValueError):
        agent.parse_plan(raw, set(agent.ACTIONS))


def test_task_store_does_not_lose_parallel_events(tmp_path):
    store = TaskStore(tmp_path/'brain.db')
    task = store.begin('owner', 'coding', 'inspect', str(tmp_path), 'runtime')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: store.event(task['id'], 'check', str(n)), range(30)))
    assert len(store.get(task['id'])['events']) == 30
