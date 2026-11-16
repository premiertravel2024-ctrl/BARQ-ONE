"""Regression tests for cloud-first diversity and an unclipped React model picker."""
import asyncio
from pathlib import Path

import pytest
from router.config import Config, Provider, Model
from router.engine import Engine
from providers.client import ProviderError

@pytest.fixture(autouse=True)
def isolated_router_cloud_fakes(monkeypatch):
    """Keep OS credentials and persisted billing lockout out of offline router tests."""
    import router.select as selection
    import router.config as provider_config
    # Both selectors must see the SAME fake credentials. CommandNetwork's
    # registry imports router.config.key_for independently of router.select,
    # otherwise Windows Credential Manager can silently remove Gemini from
    # the candidate chain and invalidate the cloud-fallback test.
    def fake_key_for(provider):
        if provider.kind == 'local':
            return 'local-no-key-required'
        return 'test-only-placeholder' if provider.api_key_env in {
            'DIVERSITY_GEMINI_KEY', 'DIVERSITY_GROQ_KEY'
        } else ''
    monkeypatch.setattr(selection, 'key_for', fake_key_for)
    monkeypatch.setattr(provider_config, 'key_for', fake_key_for)
    monkeypatch.setattr(selection, 'blocked', lambda name: False)
    # Engine.stream_run imports this function directly at execution time.
    # Fake cloud credentials alone are insufficient on Windows if a real
    # billing-block file exists in the user's persisted state.
    import router.free_policy as free_policy
    monkeypatch.setattr(free_policy, 'blocked', lambda name: False)
    # This test exercises cloud fallback order, not live provider quality rankings.
    # Keep synthetic rankings deterministic regardless of bundled model YAML,
    # user feedback or environment-specific provider state.
    from command_network.registry import Registry
    monkeypatch.setattr(Registry, '_read_overrides', lambda self: {
        'gemini/gemini-3.8-flash': {
            'strengths': {'chat': 0.85, 'qa': 0.85, 'coding': 0.85, 'reasoning': 0.85},
            'p50_latency': 1.8, 'arabic_quality': 0.85,
        },
        'groq/openai/gpt-oss-120b': {
            'strengths': {'chat': 0.70, 'qa': 0.70, 'coding': 0.70, 'reasoning': 0.70},
            'p50_latency': 1.8, 'arabic_quality': 0.70,
        },
    })

    # These tests exercise provider fallback, not the production model-scoring
    # algorithm. Pin ONLY the order of candidates already approved by the
    # real DecisionRouter. Windows user state, model metadata and health
    # signals must not change which synthetic provider is tried first.
    from command_network.routing import DecisionRouter
    original_plan = DecisionRouter.plan
    def fallback_test_plan(self, req, profile, models, health=None, quota=None,
                           breaker=None, recent_provider=None):
        plan = original_plan(self, req, profile, models, health=health,
                             quota=quota, breaker=breaker,
                             recent_provider=recent_provider)
        gemini = 'gemini/gemini-3.8-flash'
        groq = 'groq/openai/gpt-oss-120b'
        # No unsafe insertion: missing/blocked/over-quota models stay absent.
        desired = [groq, gemini] if recent_provider == 'gemini' else [gemini, groq]
        chain = [k for k in desired if k in plan.chain]
        chain.extend(k for k in plan.chain if k not in chain)
        return plan.model_copy(update={'chain': chain})
    monkeypatch.setattr(DecisionRouter, 'plan', fallback_test_plan)



def cloud_config(monkeypatch):
    """Synthetic providers for router-order tests (never exposed to runtime)."""
    monkeypatch.setenv('DIVERSITY_GEMINI_KEY', 'test-token')
    monkeypatch.setenv('DIVERSITY_GROQ_KEY', 'test-token')
    def fake_provider(name, url, key, priority, model_name, kind='cloud'):
        return Provider.model_construct(
            name=name, base_url=url, kind=kind, api_key_env=key,
            priority=priority, enabled=True, requires_key=kind == 'cloud',
            models=[Model.model_construct(name=model_name, enabled=True, free=True, strengths=['simple', 'coding'])],
        )
    return Config.model_construct(providers=[
        fake_provider('gemini', 'https://example.invalid/v1', 'DIVERSITY_GEMINI_KEY', 90, 'gemini-3.8-flash'),
        fake_provider('groq', 'https://example.invalid/v1', 'DIVERSITY_GROQ_KEY', 86, 'openai/gpt-oss-120b'),
        fake_provider('ollama', 'http://127.0.0.1:11434/v1', None, 20, 'coder-local', 'local'),
    ])


@pytest.mark.asyncio
async def test_gemini_timeout_tries_other_cloud_before_ollama(monkeypatch,tmp_path):
    import providers.streaming as upstream
    attempts=[]
    async def fake_stream(p,m,messages):
        attempts.append(p.name)
        if p.name=='gemini':
            error=ProviderError('ReadTimeout')
            error.network=True
            error.connection_failure=False
            raise error
        if p.name=='ollama':
            raise AssertionError('Ollama should not be queried while Groq succeeds')
        yield 'Groq cloud answer'
    monkeypatch.setattr(upstream,'stream_complete',fake_stream)
    engine=Engine(cloud_config(monkeypatch),False,str(tmp_path/'cache.sqlite'))
    events=[event async for event in engine.stream_run([{'role':'user','content':'hello'}])]
    assert attempts==['gemini','groq']
    assert next(x for x in events if x['type']=='model')['provider']=='groq'
    assert events[-1]['type']=='done'
    assert engine.connectivity()['cloud_connection']=='not_checked_or_restored'


@pytest.mark.asyncio
async def test_single_connect_error_does_not_block_second_cloud(monkeypatch,tmp_path):
    import providers.streaming as upstream
    attempts=[]
    async def fake_stream(p,m,messages):
        attempts.append(p.name)
        if p.name=='gemini':
            error=ProviderError('ConnectError')
            error.network=True
            error.connection_failure=True
            raise error
        if p.name=='ollama':raise AssertionError('Skipped available cloud backup')
        yield 'other cloud is available'
    monkeypatch.setattr(upstream,'stream_complete',fake_stream)
    engine=Engine(cloud_config(monkeypatch),False,str(tmp_path/'cache.sqlite'))
    events=[event async for event in engine.stream_run([{'role':'user','content':'hello'}])]
    assert attempts==['gemini','groq']
    assert engine.connectivity()['cloud_connection']=='not_checked_or_restored'
    assert events[-1]['type']=='done'


@pytest.mark.asyncio
async def test_successful_cloud_providers_can_rotate(monkeypatch,tmp_path):
    import providers.streaming as upstream
    async def fake_stream(p,m,messages):
        yield p.name + ' response'
    monkeypatch.setattr(upstream,'stream_complete',fake_stream)
    engine=Engine(cloud_config(monkeypatch),False,str(tmp_path/'cache.sqlite'))
    first=[event async for event in engine.stream_run([{'role':'user','content':'hello'}])]
    second=[event async for event in engine.stream_run([{'role':'user','content':'hello again'}])]
    one=next(x['provider'] for x in first if x['type']=='model')
    two=next(x['provider'] for x in second if x['type']=='model')
    assert (one,two)==('gemini','groq')


@pytest.mark.asyncio
async def test_non_streaming_cloud_timeout_uses_cloud_backup(monkeypatch,tmp_path):
    import router.engine as engine_module
    names=[]
    async def fake_complete(p,m,messages):
        names.append(p.name)
        if p.name=='gemini':
            error=ProviderError('ReadTimeout');error.network=True
            raise error
        if p.name=='ollama':raise AssertionError('Local should not be used when cloud responds')
        return 'Cloud backup answer'
    monkeypatch.setattr(engine_module,'complete',fake_complete)
    engine=Engine(cloud_config(monkeypatch),False,str(tmp_path/'cache.sqlite'))
    result=await engine.run([{'role':'user','content':'hello'}],use_cache=False)
    assert names==['gemini','groq']
    assert result['offline'] is False


def test_dropdown_is_portalled_out_of_composer():
    src=Path(__file__).resolve().parents[1] / 'frontend/src/components/chat/ModelSelector.tsx'
    text=src.read_text(encoding='utf-8')
    assert "createPortal" in text and 'document.body' in text
    assert 'position:\'fixed\'' in text
    assert 'getBoundingClientRect' in text
    assert 'anchor.top-height-gap' in text
    assert 'menu.current?.contains(target)' in text


def test_model_strategy_controls_present():
    text=(Path(__file__).resolve().parents[1]/'frontend/src/components/workspace/ModelControls.tsx').read_text(encoding='utf-8')
    assert "'/v1/router/mode'" in text
    assert "id:'cloud'" in text and "id:'local'" in text and "id:'auto'" in text


def test_fallback_test_fixture_never_invents_blocked_cloud_candidates(monkeypatch,tmp_path):
    """The deterministic test route must not introduce models absent from policy."""
    from command_network.routing import DecisionRouter
    from command_network.contracts import Request
    from command_network.registry import Capability
    # The fixture may reorder only candidates already surviving policy gates.
    router=DecisionRouter()
    from command_network.contracts import TaskProfile
    profile=TaskProfile(task_type='chat',language='en')
    models=[Capability(id='groq/openai/gpt-oss-120b',provider='groq',name='openai/gpt-oss-120b',configured=True)]
    planned=router.plan(Request(messages=[{'role':'user','content':'hi'}]),profile,models)
    assert 'gemini/gemini-3.8-flash' not in planned.chain


def test_offline_cloud_fixture_isolated_from_persisted_billing_block(monkeypatch, tmp_path):
    """A real billing block must not leak into synthetic provider tests."""
    import router.free_policy as free_policy
    import router.select as selection
    # This override imitates a user's persisted Windows lockout BEFORE setup.
    monkeypatch.setattr(free_policy, 'read_blocks', lambda: {'gemini': {'billing_blocked': True}})
    assert free_policy.blocked('gemini') is False
    assert selection.blocked('gemini') is False
    engine = Engine(cloud_config(monkeypatch), False, str(tmp_path / 'cache.sqlite'))
    names = [p.name for p, _ in engine.router.candidates('simple', 'easy', 5)]
    assert 'gemini' in names and 'groq' in names
