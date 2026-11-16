import pytest
from fastapi.testclient import TestClient
from router.config import Config
from router.engine import Engine
from api import app


def local_config():
    return Config.model_validate({'providers':[{'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1','models':[]}]})


@pytest.mark.asyncio
async def test_offline_local_server_reports_clear_action(monkeypatch,tmp_path):
    import router.engine as engine_mod
    async def offline(_url):raise ConnectionError('not running')
    monkeypatch.setattr(engine_mod,'discover_models',offline)
    engine=Engine(local_config(),cache_path=str(tmp_path/'cache.sqlite'))
    results=[item async for item in engine.stream_run([{'role':'user','content':'hi'}])]
    assert results[-1]['type']=='error'
    assert 'Ollama is not responding' in results[-1]['message']


@pytest.mark.asyncio
async def test_empty_ollama_model_list_gives_specific_message(monkeypatch,tmp_path):
    import router.engine as engine_mod
    async def no_models(_url):return []
    monkeypatch.setattr(engine_mod,'discover_models',no_models)
    engine=Engine(local_config(),cache_path=str(tmp_path/'cache.sqlite'))
    results=[item async for item in engine.stream_run([{'role':'user','content':'hi'}])]
    assert 'no local model is installed' in results[-1]['message']


def test_unreachable_local_provider_not_reported_ready(monkeypatch):
    from api import engine
    monkeypatch.setattr(engine,'_ollama_online',False)
    monkeypatch.setattr(engine,'_ollama_error','Ollama connection refused')
    async def no_probe(force=False):return None
    monkeypatch.setattr(engine,'refresh_local',no_probe)
    response=TestClient(app).get('/v1/router/providers')
    assert response.status_code==200
    local=next(item for item in response.json()['providers'] if item['kind']=='local')
    assert local['configured'] is True
    assert local['ready'] is False
    assert 'refused' in local['status_message']
