"""Model coordination: a downloaded local coding planner precedes bounded free clouds."""
import json
from unittest.mock import AsyncMock

import pytest

from router.config import Config, Model
from router.engine import Engine, AllModelsFailed
from providers.client import ProviderError


def fixture_engine(tmp_path, monkeypatch):
    monkeypatch.setenv('BARQ_TEST_CLOUD_KEY', 'fake-test-key')
    monkeypatch.setenv('BARQ_PROVIDER_RETRIES', '0')
    config = Config.model_validate({'providers': [
        {'name':'groq','base_url':'https://api.groq.com/openai/v1',
         'api_key_env':'BARQ_TEST_CLOUD_KEY', 'priority':80,
         'models':[{'name':'free-coder','strengths':['coding'],'context_window':32768}]},
        {'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1',
         'priority':10,'models':[{'name':'qwen3:4b','strengths':['coding'],'context_window':32768}]},
    ]})
    engine = Engine(config, cache_path=str(tmp_path/'cache.sqlite3'))
    # Provider discovery is tested separately. No actual network is allowed.
    engine.refresh_local = AsyncMock(return_value=config.providers[1])
    return engine


def validate_plan(text):
    value=json.loads(text)
    if not value.get('steps'):raise ValueError('empty tool plan')
    return value


@pytest.mark.asyncio
async def test_auto_coding_plan_uses_ready_ollama_before_cloud(tmp_path,monkeypatch):
    engine=fixture_engine(tmp_path,monkeypatch)
    calls=[]
    async def fake_complete(provider,model,messages):
        calls.append(provider.name)
        if provider.kind!='local':raise AssertionError('Cloud was contacted despite successful local plan')
        return '{"steps":[{"tool":"workspace_read","args":{"path":"main.py"}}]}'
    monkeypatch.setattr('router.engine.complete',fake_complete)
    result=await engine.run([{'role':'user','content':'ابني التطبيق'}],model='auto',use_cache=False,
                            task_hint='coding',response_validator=validate_plan)
    assert result['offline'] is True
    assert calls==['ollama']
    engine.refresh_local.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_local_plan_falls_back_once_to_cloud(tmp_path,monkeypatch):
    engine=fixture_engine(tmp_path,monkeypatch)
    calls=[]
    async def fake_complete(provider,model,messages):
        calls.append(provider.name)
        if provider.kind=='local':return '{"steps":[]}'
        return '{"steps":[{"tool":"workspace_read","args":{"path":"main.py"}}]}'
    monkeypatch.setattr('router.engine.complete',fake_complete)
    result=await engine.run([{'role':'user','content':'ابني التطبيق'}],model='auto',use_cache=False,
                            task_hint='coding',response_validator=validate_plan)
    assert result['offline'] is False
    assert calls==['ollama','groq']
    assert len(result['attempts'])==1


@pytest.mark.asyncio
async def test_manual_cloud_model_never_queries_local(tmp_path,monkeypatch):
    engine=fixture_engine(tmp_path,monkeypatch)
    calls=[]
    async def fake_complete(provider,model,messages):
        calls.append(provider.name)
        return '{"steps":[{"tool":"workspace_read","args":{"path":"main.py"}}]}'
    monkeypatch.setattr('router.engine.complete',fake_complete)
    await engine.run([{'role':'user','content':'ابني التطبيق'}],model='groq/free-coder',use_cache=False,
                     task_hint='coding',response_validator=validate_plan)
    assert calls==['groq']
    engine.refresh_local.assert_not_called()


@pytest.mark.asyncio
async def test_all_model_errors_stay_explicit_and_local_does_not_loop(tmp_path,monkeypatch):
    engine=fixture_engine(tmp_path,monkeypatch)
    calls=[]
    async def fake_complete(provider,model,messages):
        calls.append(provider.name)
        raise ProviderError('temporarily unavailable',status=503)
    monkeypatch.setattr('router.engine.complete',fake_complete)
    with pytest.raises(AllModelsFailed) as got:
        await engine.run([{'role':'user','content':'ابني التطبيق'}],model='auto',use_cache=False,
                         task_hint='coding',response_validator=validate_plan)
    assert calls==['ollama','groq']
    assert len(got.value.attempts)==2
