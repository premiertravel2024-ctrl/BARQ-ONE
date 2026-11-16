"""Contract-level integration tests for the new React -> FastAPI bridge.

Real cloud calls, Windows builds and browser rendering need separate environment tests.
"""
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
import api

ROOT=Path(__file__).resolve().parents[1]


def test_router_chat_sse_emits_real_model_fallback_and_content(monkeypatch):
    called=[]
    async def fake_stream(messages,model='auto',**kwargs):
        called.append((messages,model))
        yield {'type':'routing','status':'Trying Gemini'}
        yield {'type':'routing','status':'Trying Ollama after fallback'}
        yield {'type':'model','model':'ollama/qwen2.5-coder:7b',
               'attempts':['gemini/gemini-3.8-flash: rate limit'],
               'provider':'ollama','offline':True,'cached':False,'task':'coding'}
        yield {'type':'token','content':'مراجعة '}
        yield {'type':'token','content':'الكود ناجحة'}
        yield {'type':'metrics','latency_seconds':0.3,'time_to_first_token_seconds':0.1,
               'characters_per_second':60.0,'output_characters':18}
        yield {'type':'done','finish_reason':'stop'}
    monkeypatch.setattr(api.engine,'stream_run',fake_stream)
    with TestClient(api.app) as client:
        response=client.post('/v1/router/chat/stream',json={'model':'auto','messages':[{'role':'user','content':'افحص الكود'}]})
    assert response.status_code==200,response.text
    assert response.headers['content-type'].startswith('text/event-stream')
    assert 'event: model' in response.text
    assert 'ollama/qwen2.5-coder:7b' in response.text
    assert 'gemini/gemini-3.8-flash: rate limit' in response.text
    assert 'event: token' in response.text
    assert 'مراجعة ' in response.text and 'الكود ناجحة' in response.text
    assert 'event: done' in response.text
    assert called[0][1]=='auto'
    assert called[0][0][-1]['content']=='افحص الكود'


def test_chat_stream_validates_input_before_routing():
    with TestClient(api.app) as client:
        response=client.post('/v1/router/chat/stream',json={'messages':[]})
    assert response.status_code==422


def test_chat_stream_rejects_missing_local_model(monkeypatch):
    async def refresh(*args,**kwargs):pass
    monkeypatch.setattr(api.engine,'refresh_local',refresh)
    monkeypatch.setattr(api.engine.config,'providers',[],raising=False)
    with TestClient(api.app) as client:
        response=client.post('/v1/router/chat/stream',json={'model':'local-only','messages':[{'role':'user','content':'Offline'}]})
    assert response.status_code==503
    assert 'Ollama' in response.text


def test_new_react_ui_does_not_use_mock_service_in_chat_flow():
    chat=(ROOT/'frontend/src/lib/chat.ts').read_text(encoding='utf-8')
    backend=(ROOT/'frontend/src/lib/backend.ts').read_text(encoding='utf-8')
    studio=(ROOT/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    legacy_tools=(ROOT/'frontend/src/components/workspace/WorkspaceTools.tsx').read_text(encoding='utf-8')
    assert '<WorkspaceTools open inside' in studio
    studio += legacy_tools
    assert "from './mockAI'" not in chat
    assert "from './backend'" in chat
    assert '/v1/router/chat/stream' in backend
    assert '/v1/agent/plan' in studio
    assert '/v1/agent/execute' in studio
    assert '/v1/workspace/edit/apply' in studio
    assert '/v1/build/preview' in studio


def test_model_keys_only_go_to_backend():
    source=(ROOT/'frontend/src/components/workspace/ModelControls.tsx').read_text(encoding='utf-8')
    assert '/v1/settings/key' in source
    assert 'localStorage' not in source
    assert 'getItem' not in source
