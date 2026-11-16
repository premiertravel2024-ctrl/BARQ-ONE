"""Offline routing contract. No live service or network required for this suite."""
import pytest
from fastapi.testclient import TestClient
from api import app
from router.config import Config, key_for
from router.engine import Engine, AllModelsFailed
from providers.ollama import installed_model_names, verified_base_url
from router.config import Model


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv('OFFLINE_TEST_CLOUD_KEY', 'fake-for-unit-tests')
    return Config.model_validate({'providers': [
        {'name':'testcloud','kind':'cloud','base_url':'https://example.invalid/v1',
         'api_key_env':'OFFLINE_TEST_CLOUD_KEY','priority':90,'models':[{'name':'cloud-example'}]},
        {'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1',
         'priority':20,'rpm':0,'rpd':0,'models':[]}
    ]})


def test_only_safe_local_endpoint():
    assert verified_base_url('http://localhost:11434/v1')=='http://localhost:11434/v1'
    assert verified_base_url('http://127.0.0.1:11434')=='http://127.0.0.1:11434/v1'
    for bad in ('https://localhost:11434/v1','http://public.example:11434/v1',
                'http://127.0.0.1:11434/admin','http://user:password@localhost:11434/v1',
                'http://192.168.1.2:11434/v1'):
        with pytest.raises(ValueError):
            verified_base_url(bad)


def test_never_include_cloud_only_ollama_models():
    result=installed_model_names({'models':[
        {'name':'qwen2.5-coder:7b'},
        {'name':'gpt-oss:120b-cloud'},
        {'model':'gemma3:4b'},
        {'name':'qwen2.5-coder:7b'}
    ]})
    assert result==['qwen2.5-coder:7b','gemma3:4b']


def test_ollama_has_no_api_key(cfg):
    assert key_for(cfg.providers[1]) == 'local-no-key-required'
    assert not cfg.providers[1].models


@pytest.mark.asyncio
async def test_cloud_network_failure_uses_local(monkeypatch,tmp_path,cfg):
    import router.engine as engine_module
    async def fake_discover(url):
        return [Model(name='qwen2.5-coder:7b',strengths=['coding'])]
    seen=[]
    async def fake_complete(p,m,messages):
        seen.append(p.name)
        if p.kind=='cloud':
            err=engine_module.ProviderError('Network unplugged')
            err.network=True
            raise err
        return 'Offline generated answer'
    monkeypatch.setattr(engine_module,'discover_models',fake_discover)
    monkeypatch.setattr(engine_module,'complete',fake_complete)
    e=Engine(cfg,False,str(tmp_path/'cache.db'))
    result=await e.run([{'role':'user','content':'Write Python code'}])
    assert result['offline'] is True
    assert result['model']=='ollama/qwen2.5-coder:7b'
    assert seen==['testcloud','ollama']
    # One failed cloud provider is not proof the entire network is offline.
    assert e.connectivity()['cloud_connection']=='not_checked_or_restored'
    # Next prompt during the outage starts with local provider and doesn't hit cloud.
    seen.clear()
    result=await e.run([{'role':'user','content':'another prompt'}])
    assert result['offline'] is True
    assert seen==['ollama']


@pytest.mark.asyncio
async def test_explicit_local_does_not_call_cloud(monkeypatch,tmp_path,cfg):
    import router.engine as engine_module
    async def fake_discover(url):
        return [Model(name='local:latest',strengths=['simple'])]
    async def fake_complete(p,m,messages):
        assert p.kind=='local'
        return 'Answered locally'
    monkeypatch.setattr(engine_module,'discover_models',fake_discover)
    monkeypatch.setattr(engine_module,'complete',fake_complete)
    e=Engine(cfg,False,str(tmp_path/'cache.db'))
    result=await e.run([{'role':'user','content':'hi'}],model='ollama/local:latest')
    assert result['model']=='ollama/local:latest'


@pytest.mark.asyncio
async def test_no_cloud_key_still_uses_local(monkeypatch,tmp_path):
    import router.engine as engine_module
    config=Config.model_validate({'providers':[{'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1','models':[]}]})
    async def fake_discover(url):return [Model(name='tiny:latest')]
    async def fake_complete(p,m,messages):return 'Local reply'
    monkeypatch.setattr(engine_module,'discover_models',fake_discover)
    monkeypatch.setattr(engine_module,'complete',fake_complete)
    e=Engine(config,False,str(tmp_path/'cache.db'))
    assert (await e.run([{'role':'user','content':'hello'}]))['offline']


@pytest.mark.asyncio
async def test_local_only_never_uses_cloud(monkeypatch,tmp_path,cfg):
    import router.engine as engine_module
    async def fake_discover(url):return [Model(name='tiny:latest')]
    async def fake_complete(p,m,messages):
        if p.kind!='local':raise AssertionError('Cloud call in local-only mode')
        return 'Local reply'
    monkeypatch.setattr(engine_module,'discover_models',fake_discover)
    monkeypatch.setattr(engine_module,'complete',fake_complete)
    e=Engine(cfg,True,str(tmp_path/'cache.db'))
    assert (await e.run([{'role':'user','content':'hello'}]))['model']=='ollama/tiny:latest'


def test_connectivity_api_does_not_expose_model_keys():
    client=TestClient(app)
    result=client.get('/v1/router/connectivity')
    assert result.status_code==200
    info=result.json()
    assert info['mode'] in ('auto','local','cloud')
    assert 'ollama' in info and 'models' in info['ollama']
    assert 'api_key' not in result.text.lower()
