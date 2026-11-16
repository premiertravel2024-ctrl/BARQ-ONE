"""Cloud integration regression suite: deterministic, never sends real requests."""
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from providers.discovery import CloudInspector, endpoint_for, validated_chat_url
from router.config import Provider, Model

@pytest.fixture(autouse=True)
def isolated_cloud_credentials(monkeypatch):
    """Use only test credentials, never Windows Credential Manager or live keys."""
    import providers.discovery as discovery
    monkeypatch.setattr(discovery, 'key_for',
                        lambda provider: __import__('os').environ.get('BARQ_CLOUD_TEST_TOKEN', ''))



def make_provider(name='gemini', url='https://generativelanguage.googleapis.com/v1beta/openai', models=None):
    """Offline discovery fixture, independent of mutable runtime provider catalog.

    These tests exercise endpoint verification, not the Free Guard. Production
    provider construction still goes through Config validation and the allowlist.
    """
    entries = models or [{'name': 'gemini-3.8-flash'}]
    return Provider.model_construct(
        name=name, base_url=url, kind='cloud', api_key_env='BARQ_CLOUD_TEST_TOKEN',
        enabled=True, priority=50, free_status='unverified', requires_key=True,
        models=[Model.model_construct(name=item['name'], enabled=True, free=True,
                                      strengths=item.get('strengths', [])) for item in entries],
    )


@pytest.mark.asyncio
async def test_gemini_key_verified_by_model_list_not_text_prompt(monkeypatch):
    token='never-send-to-user-987'
    monkeypatch.setenv('BARQ_CLOUD_TEST_TOKEN', token)
    provider=make_provider()
    seen=[]
    def get_models(request):
        seen.append(request)
        assert request.url.path=='/v1beta/openai/models'
        assert request.headers['Authorization']=='Bearer '+token
        assert request.method=='GET'
        return httpx.Response(200,json={'object':'list','data':[{'id':'gemini-3.8-flash'},{'id':'other-model'}]})
    checker=CloudInspector()
    value=await checker.check(provider,transport=httpx.MockTransport(get_models))
    assert value['verified'] and value['models']==['gemini-3.8-flash']
    assert value['status']=='verified'
    assert token not in str(value)
    assert len(seen)==1


@pytest.mark.asyncio
async def test_auth_failure_is_clearly_reported_and_secret_hidden(monkeypatch):
    monkeypatch.setenv('BARQ_CLOUD_TEST_TOKEN','test-secret')
    checker=CloudInspector()
    response=await checker.check(make_provider(),transport=httpx.MockTransport(
        lambda request:httpx.Response(401,text='this is your test-secret')))
    assert response['status']=='auth_error' and not response['verified']
    assert 'test-secret' not in str(response)


@pytest.mark.asyncio
async def test_rate_limit_does_not_claim_online(monkeypatch):
    monkeypatch.setenv('BARQ_CLOUD_TEST_TOKEN','test-secret')
    response=await CloudInspector().check(make_provider(),transport=httpx.MockTransport(
        lambda request:httpx.Response(429,text='too many requests')))
    assert response['status']=='rate_limited'
    assert response['verified'] is False


@pytest.mark.asyncio
async def test_missing_key_does_not_start_network(monkeypatch):
    monkeypatch.delenv('BARQ_CLOUD_TEST_TOKEN',raising=False)
    monkeypatch.setattr('providers.discovery.key_for',lambda provider:'')
    def no_network(request):raise AssertionError('Missing-key request should never touch network')
    result=await CloudInspector().check(make_provider(),transport=httpx.MockTransport(no_network))
    assert result['status']=='missing_key'


@pytest.mark.asyncio
async def test_untrusted_gemini_endpoint_rejected_before_sending_key(monkeypatch):
    monkeypatch.setenv('BARQ_CLOUD_TEST_TOKEN','secret')
    provider=make_provider(url='https://evil.example/v1beta/openai')
    def fail(request):raise AssertionError('A secret was sent to an untrusted endpoint')
    result=await CloudInspector().check(provider,transport=httpx.MockTransport(fail))
    assert result['status']=='config_error'
    with pytest.raises(ValueError,match='Untrusted'):
        validated_chat_url(provider)


@pytest.mark.asyncio
async def test_openrouter_adds_only_free_models(monkeypatch):
    monkeypatch.setenv('BARQ_CLOUD_TEST_TOKEN','key')
    p=make_provider('openrouter','https://openrouter.ai/api/v1',models=[{'name':'openrouter/free'}])
    result=await CloudInspector().check(p,transport=httpx.MockTransport(lambda request:httpx.Response(200,json={
       'data':[{'id':'provider/paid'}, {'id':'provider/free:free'}, {'id':'vendor/coder:free'}]})))
    assert result['verified'] and 'openrouter/free' in result['models']
    assert set(result['free_models'])=={'provider/free:free','vendor/coder:free'}
    assert not any('paid' in name for name in result['free_models'])


def test_groq_and_openrouter_use_correct_secure_endpoints():
    groq=make_provider('groq','https://api.groq.com/openai/v1',[{'name':'openai/gpt-oss-120b'}])
    router=make_provider('openrouter','https://openrouter.ai/api/v1',[{'name':'openrouter/free'}])
    assert endpoint_for(groq)=='https://api.groq.com/openai/v1/models'
    assert validated_chat_url(router)=='https://openrouter.ai/api/v1/chat/completions'


def test_local_api_exposes_explicit_cloud_check_endpoints(monkeypatch):
    import api
    provider=next(p for p in api.engine.config.providers if p.name=='gemini')
    async def fake_check(p,*,timeout=9,transport=None):
        assert p==provider
        record={'provider':p.name,'verified':True,'status':'verified','message':'Checked',
                'models':['gemini-3.8-flash'],'free_models':[],'checked_at':__import__('time').time()}
        api.cloud_inspector.statuses[p.name]=record
        return record
    monkeypatch.setattr(api.cloud_inspector,'check',fake_check)
    monkeypatch.setattr(api.engine,'refresh_local',lambda *args,**kwargs: fake_refresh())
    with TestClient(api.app) as client:
        response=client.post('/v1/cloud/check',json={'provider':'gemini'})
        assert response.status_code==200,response.text
        assert response.json()['verified'] is True
        status=client.get('/v1/router/providers')
        assert status.status_code==200
        gemini=next(p for p in status.json()['providers'] if p['name']=='gemini')
        assert gemini['verification_status']=='verified'
        response=client.post('/v1/cloud/check',json={'provider':'fake-provider'})
        assert response.status_code==404
    api.cloud_inspector.forget('gemini')


async def fake_refresh():return None


def test_frontend_contains_live_probe_and_key_settings():
    source=(Path(__file__).resolve().parents[1]/'frontend/src/components/workspace/ModelControls.tsx').read_text(encoding='utf-8')
    assert '/v1/cloud/check' in source and '/v1/cloud/check-all' in source
    assert '/v1/settings/key' in source and '/v1/models/test' in source
    assert 'localStorage' not in source
