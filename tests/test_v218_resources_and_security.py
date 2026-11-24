import json
import pytest
import httpx
from fastapi.testclient import TestClient
from core.adaptive_resources import AdaptiveResources
from router.config import Model,Provider,Config
from providers.reliability import retry_delay,retry_limit,setting


@pytest.mark.parametrize('free,mode,expected',[(256*1024**2,'performance',2048),(2*1024**3,'balanced',4096),(16*1024**3,'eco',4096),(16*1024**3,'performance',16384)])
def test_local_context_adapts_to_ram_and_profile(tmp_path,monkeypatch,free,mode,expected):
    monkeypatch.delenv('OLLAMA_NUM_CTX',raising=False)
    resources=AdaptiveResources(tmp_path/'resources.json',sampler=lambda:{'ram_available_bytes':free,'logical_cpu_cores':4,'cpu_load_percent':5})
    resources.set_mode(mode)
    assert resources.ollama_context(Model(name='local',context_window=65536))==expected
    assert resources.ollama_context(Model(name='small',context_window=1024))==1024


def test_retry_backoff_is_bounded_with_jitter(monkeypatch):
    monkeypatch.setenv('BARQ_RETRY_BASE_SECONDS','0.5')
    monkeypatch.setenv('BARQ_RETRY_MAX_SECONDS','4')
    for attempt in range(8):
        values=[retry_delay(attempt) for _ in range(20)]
        assert len(set(values))>1
        assert all(.25<=v<=min(4,.5*2**attempt) for v in values)
    monkeypatch.setenv('BARQ_PROVIDER_RETRIES','900')
    assert retry_limit()==3
    monkeypatch.setenv('BARQ_PROVIDER_TIMEOUT','nan')
    assert setting('BARQ_PROVIDER_TIMEOUT',45,5,180)==45


@pytest.mark.asyncio
async def test_native_ollama_completion_uses_same_context_limit(monkeypatch,tmp_path):
    from core.adaptive_resources import resources
    import providers.client as client
    monkeypatch.setattr(resources,'snapshot',lambda:{'mode':'balanced','ram_available_bytes':512*1024**2})
    provider=Provider(name='ollama',kind='local',base_url='http://127.0.0.1:11434/v1',models=[Model(name='tiny',context_window=2048)])
    seen=[]
    def transport(req):
        data=json.loads(req.content);seen.append(data)
        assert req.url.path=='/api/chat'
        assert data['options']['num_ctx']==2048 and data['stream'] is False
        return httpx.Response(200,json={'message':{'content':'محلي'},'done':True,'eval_count':3,'prompt_eval_count':2})
    real=httpx.AsyncClient
    monkeypatch.setattr(client.httpx,'AsyncClient',lambda **kw:real(**kw,transport=httpx.MockTransport(transport)))
    result=await client.complete(provider,provider.models[0],[{'role':'user','content':'hi'}])
    assert result=='محلي' and result.usage['total_tokens']==5 and len(seen)==1


def test_loopback_ipv6_and_foreign_origins():
    import api
    with TestClient(api.app,base_url='http://localhost') as client:
        # Some httpx versions cannot parse the bracketed IPv6 base URL.
        # Test the exact IPv6 Host header against the production origin guard.
        assert client.get('/health',headers={'Host':'[::1]'}).status_code==200
        assert client.post('/v1/brain/cancel',json={'conversation_id':'none'},headers={'Host':'[::1]', 'Origin':'http://evil.invalid'}).status_code==403
    with TestClient(api.app,client=('192.168.1.10',5000)) as client:
        assert client.get('/health').status_code==403


def test_websocket_rejects_cross_origin_before_voice_handler(monkeypatch):
    import api
    from starlette.websockets import WebSocketDisconnect
    called=[]
    async def voice(ws):called.append(True)
    monkeypatch.setattr(api,'handle_live',voice)
    with TestClient(api.app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/v1/voice/live',headers={'origin':'https://evil.invalid'}):pass
    assert not called


@pytest.mark.parametrize('priority',[-1,101])
def test_provider_config_rejects_invalid_priority(priority):
    with pytest.raises(ValueError):
        Provider(name='offline-test',base_url='https://example.invalid',priority=priority,models=[])


@pytest.mark.asyncio
async def test_503_retries_are_bounded_and_429_hands_off(monkeypatch,tmp_path):
    from unittest.mock import AsyncMock
    from router.engine import Engine
    import router.engine as routing
    monkeypatch.setenv('BARQ_PROVIDER_RETRIES','2')
    config=Config.model_validate({'providers':[{'name':'ollama','kind':'local','base_url':'http://localhost:11434/v1',
        'models':[{'name':'first','strengths':['coding']},{'name':'backup','strengths':['coding']}]}]})
    engine=Engine(config,cache_path=str(tmp_path/'cache.db'))
    monkeypatch.setattr(engine,'refresh_local',AsyncMock(return_value=config.providers[0]))
    sleep=AsyncMock();monkeypatch.setattr(routing.asyncio,'sleep',sleep)
    calls=[]
    async def complete(p,m,messages):
        calls.append(m.name)
        if m.name=='first':raise routing.ProviderError('temporary error',503)
        return 'Verified free fallback'
    monkeypatch.setattr(routing,'complete',complete)
    result=await engine.run([{'role':'user','content':'Fix Python project'}],use_cache=False)
    assert result['content']=='Verified free fallback'
    assert calls==['first','first','first','backup']
    assert sleep.await_count==2
    # A fresh engine resets cooldown without mutating implementation internals.
    engine=Engine(config,cache_path=str(tmp_path/'cache2.db'))
    monkeypatch.setattr(engine,'refresh_local',AsyncMock(return_value=config.providers[0]))
    calls.clear()
    async def limited(p,m,messages):
        calls.append(m.name)
        if m.name=='first':raise routing.ProviderError('quota',429,{'retry-after':'30'})
        return 'Quota-safe fallback'
    monkeypatch.setattr(routing,'complete',limited)
    from router.engine import AllModelsFailed
    with pytest.raises(AllModelsFailed):
        await engine.run([{'role':'user','content':'Fix Python project'}],use_cache=False)
    assert calls==['first'], 'Retry-After must block every model sharing the same quota scope'


def test_loopback_guard_blocks_malformed_origin_and_cross_site_writes():
    import api

    with TestClient(api.app, base_url='http://localhost') as client:
        assert client.post('/v1/brain/cancel', headers={'Origin': 'http://['}).status_code == 403
        assert client.post('/v1/brain/cancel', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
        response = client.get('/health')
        assert response.status_code == 200
        assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_child_environment_filters_secret_names_case_insensitively(monkeypatch):
    from core.security import child_env

    monkeypatch.setenv('provider_api_key', 'test credential')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'test credential')
    monkeypatch.setenv('BARQ_TASK', 'visible')
    env = child_env()
    assert 'provider_api_key' not in env
    assert 'AWS_SECRET_ACCESS_KEY' not in env
    assert env['BARQ_TASK'] == 'visible'
    import pytest
    with pytest.raises(ValueError):
        child_env({'service_password': 'test credential'})
