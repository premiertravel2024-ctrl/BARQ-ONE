"""Regression tests for the new BARQ AI personality, free coding discovery, and cloud TTFT fallback."""
import asyncio
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from core.persona import IDENTITY, with_identity
from providers.discovery import CloudInspector
from router.config import Config, key_for
from router.engine import Engine


def test_persona_is_first_and_non_mutating():
    source = [{'role': 'user', 'content': 'انت مين؟'}]
    output = with_identity(source)
    assert output[0]['role'] == 'system'
    assert 'BARQ AI' in output[0]['content']
    assert 'ChatGPT' in output[0]['content']  # explicitly reject wrong self-identity
    assert output[-1] == source[-1] and output[-1] is not source[-1]
    assert len(source) == 1
    assert 'Egyptian' in with_identity(source, True)[0]['content']


def test_chat_api_injects_identity_for_regular_and_stream(monkeypatch):
    import api
    seen = []
    async def fake_run(messages, model='auto', **kwargs):
        seen.append(messages)
        return {'model':'openrouter/openrouter/free','content':'أنا برق AI','task':'simple','attempts':[],'latency':.1}
    async def fake_stream(messages, model='auto', **kwargs):
        seen.append(messages)
        yield {'type':'model','model':'openrouter/openrouter/free','provider':'openrouter','attempts':[],'offline':False}
        yield {'type':'token','content':'أنا برق AI'}
        yield {'type':'done','finish_reason':'stop'}
    monkeypatch.setattr(api.engine, 'run', fake_run)
    monkeypatch.setattr(api.engine, 'stream_run', fake_stream)
    with TestClient(api.app) as client:
        r = client.post('/v1/router/chat', json={'messages':[{'role':'user','content':'اشرح تصليح كود Python صغير'}]})
        assert r.status_code == 200
        r = client.post('/v1/router/chat/stream', json={'messages':[{'role':'user','content':'اشرح تصليح كود Python صغير'}]})
        assert 'أنا برق AI' in r.text
        r = client.post('/v1/chat/completions', json={'messages':[{'role':'user','content':'اشرح تصليح كود Python صغير'}]})
        assert r.status_code == 200
    assert len(seen) == 3
    assert all(batch[0]['role'] == 'system' and 'برق AI' in batch[0]['content'] for batch in seen)


@pytest.mark.asyncio
async def test_discovery_prioritizes_only_verified_free_deepseek(monkeypatch):
    monkeypatch.setenv('BARQ_TEST_OPENROUTER_KEY', 'dummy-testing-key')
    provider = Config.model_validate({'providers':[{'name':'openrouter','base_url':'https://openrouter.ai/api/v1',
        'api_key_env':'BARQ_TEST_OPENROUTER_KEY','models':[{'name':'openrouter/free'}]}]}).providers[0]
    ids = [f'provider/model-{i:02d}:free' for i in range(70)]
    ids += ['deepseek/deepseek-v4-paid', 'deepseek/deepseek-reasoner:free',
            'recursive/flint:free', 'unknown/very-fast:free']
    checker = CloudInspector()
    result = await checker.check(provider, transport=httpx.MockTransport(lambda request:
        httpx.Response(200, json={'data':[{'id':i} for i in ids]})))
    assert result['verified'] is True
    assert result['free_models'][0] == 'deepseek/deepseek-reasoner:free'
    assert 'recursive/flint:free' in result['free_models']
    assert 'deepseek/deepseek-v4-paid' not in result['free_models']
    assert all(x.endswith(':free') for x in result['free_models'])
    assert len(result['free_models']) <= 48
    # Runtime registration: coding strength is usable by task router.
    from api import _register_verified_free_models
    _register_verified_free_models(provider, result)
    coding = next(m for m in provider.models if m.name=='deepseek/deepseek-reasoner:free')
    assert 'coding' in coding.strengths


def test_config_rejects_paid_openrouter_model():
    with pytest.raises(ValueError, match='paid model blocked'):
        Config.model_validate({'providers':[{'name':'openrouter','base_url':'https://openrouter.ai/api/v1',
            'models':[{'name':'deepseek/deepseek-v4.1'}]}]})


@pytest.mark.asyncio
async def test_slow_first_token_falls_back_to_next_free_provider(monkeypatch, tmp_path):
    monkeypatch.setenv('BARQ_FREE_FIRST_TOKEN_KEY', 'dummy')
    cfg = Config.model_validate({'providers':[
        {'name':'groq','api_key_env':'BARQ_FREE_FIRST_TOKEN_KEY','base_url':'https://api.groq.com/openai/v1',
         'priority':90,'models':[{'name':'openai/gpt-oss-20b','strengths':['simple']}]},
        {'name':'openrouter','api_key_env':'BARQ_FREE_FIRST_TOKEN_KEY','base_url':'https://openrouter.ai/api/v1',
         'priority':80,'models':[{'name':'openrouter/free','strengths':['simple']}]}]})
    import providers.streaming as stream
    started = []
    async def provider(p,m,messages):
        started.append(p.name)
        if p.name == 'groq':
            await asyncio.sleep(10)
        yield 'Fast free response'
    monkeypatch.setattr(stream,'stream_complete',provider)
    import router.engine as engine_module
    real_wait=asyncio.wait_for
    async def quick_first_token(awaitable,timeout):
        return await real_wait(awaitable, timeout=.03)
    monkeypatch.setattr(engine_module.asyncio, 'wait_for', quick_first_token)
    engine=Engine(cfg,False,str(tmp_path/'router.db'))
    events=[e async for e in engine.stream_run([{'role':'user','content':'hello'}])]
    assert started == ['groq', 'openrouter']
    assert any(e.get('type')=='token' and e.get('content')=='Fast free response' for e in events)
    assert any(e.get('type')=='done' for e in events)


def test_existing_app_identity_kept_and_new_brand_used():
    root=Path(__file__).resolve().parents[1]
    installer=(root/'scripts/installer.iss').read_text(encoding='utf-8')
    assert '9BB70D04-1EC5-4BC6-B811-64B08F5C8977' in installer
    assert 'AI Router Agent' in installer  # existing local data/install directory, deliberately unchanged
    sidebar=(root/'frontend/src/components/layout/Sidebar.tsx').read_text(encoding='utf-8')
    msg=(root/'frontend/src/components/chat/Message.tsx').read_text(encoding='utf-8')
    assert 'Free cloud · Local backup' not in sidebar
    assert 'aria-label="BARQ"' in sidebar and '<BrandLockup' in sidebar
    mark=(root/'frontend/src/components/ui/BrandMark.tsx').read_text(encoding='utf-8')
    assert 'barq-mark-dark.png' in mark and 'barq-mark-light.png' in mark
    assert '<BrandMark size={26}/>' in msg and 'BARQ AI' in msg


def test_identity_is_instant_and_offline(monkeypatch):
    import api
    async def unreachable(*args, **kwargs):
        raise AssertionError('Identity question must not require a cloud call')
    monkeypatch.setattr(api.engine, 'run', unreachable)
    with TestClient(api.app) as client:
        regular=client.post('/v1/router/chat',json={'messages':[{'role':'user','content':'انت عارف انت مين؟'}]})
        assert regular.status_code==200
        assert regular.json()['model']=='BARQ-AI/local'
        assert 'برق AI' in regular.json()['content']
        streamed=client.post('/v1/router/chat/stream',json={'messages':[{'role':'user','content':'هل انت ChatGPT؟'}]})
        assert streamed.status_code==200
        assert 'event: model' in streamed.text and 'برق AI' in streamed.text
        assert 'event: done' in streamed.text
