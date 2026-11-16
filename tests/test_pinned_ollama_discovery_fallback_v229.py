"""A transient discovery failure must not silently drop an explicit local choice."""
import json

import httpx
import pytest

from router.config import Config, Model, Provider
from router.engine import Engine, AllModelsFailed
from tests.test_v219_command_intake import controlled_http


@pytest.mark.asyncio
async def test_pinned_local_tries_loopback_chat_when_tags_temporarily_fails(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path / 'state'))
    engine = Engine(Config(providers=[Provider(
        name='ollama', kind='local', base_url='http://127.0.0.1:11434/v1',
        models=[Model(name='qwen3:4b', context_window=32768, strengths=['coding'])],
    )]), cache_path=str(tmp_path / 'cache.db'))
    requests = []
    def respond(request):
        requests.append((request.method, request.url.path))
        if request.url.path == '/api/tags':
            return httpx.Response(503, text='loading')
        assert request.url.path == '/api/chat'
        assert json.loads(request.content)['model'] == 'qwen3:4b'
        return httpx.Response(200, json={'message': {'content': 'Working locally'}, 'done': True})
    controlled_http(monkeypatch, respond)
    result = await engine.run([{'role': 'user', 'content': 'Say hello'}], model='ollama/qwen3:4b', use_cache=False)
    assert result['content'] == 'Working locally'
    assert requests == [('GET', '/api/tags'), ('POST', '/api/chat')]
    assert engine.connectivity()['ollama']['reachable'] is False
    assert engine.connectivity()['ollama']['models'] == []


@pytest.mark.asyncio
async def test_auto_does_not_try_undiscovered_model(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path / 'state'))
    engine = Engine(Config(providers=[Provider(
        name='ollama', kind='local', base_url='http://127.0.0.1:11434/v1',
        models=[Model(name='qwen3:4b', context_window=32768, strengths=['coding'])],
    )]), cache_path=str(tmp_path / 'cache.db'))
    requests=[]
    def respond(request):
        requests.append(request.url.path)
        if request.url.path == '/api/tags':
            return httpx.Response(503)
        raise AssertionError('Auto must not try an unverified local model')
    controlled_http(monkeypatch, respond)
    with pytest.raises(AllModelsFailed):
        await engine.run([{'role': 'user', 'content': 'Say hello'}], model='auto', use_cache=False)
    assert '/api/chat' not in requests
