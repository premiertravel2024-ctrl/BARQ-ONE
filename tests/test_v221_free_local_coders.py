"""No-key, no-phantom-model regression tests for BARQ coding agents."""
from unittest.mock import AsyncMock
import json
import pytest

from providers.local_coding_catalog import LOCAL_CODERS, catalog, coding_rank
from providers.ollama import installed_model_names
from router.config import Config
from router.engine import Engine


def test_catalog_is_local_keyless_and_install_is_opt_in():
    items=catalog([])
    assert len(items)>=3
    assert not any(m['installed'] for m in items)
    assert all(m['local_only'] and m['requires_api_key'] is False for m in items)
    assert all(m['install_command']=='ollama pull '+m['name'] for m in items)
    assert all(m['size_gb']<=8 for m in items)
    assert 'qwen2.5-coder:7b' in {m['name'] for m in items}


def test_catalog_only_marks_real_installed_models():
    items=catalog(['deepseek-coder:6.7b','qwen3:4b'])
    assert {item['name'] for item in items if item['installed']}=={'deepseek-coder:6.7b','qwen3:4b'}


def test_qwen_latest_alias_is_recognized_as_seven_b():
    items=catalog(['qwen2.5-coder:latest'])
    assert any(item['name']=='qwen2.5-coder:7b' and item['installed'] for item in items)


def test_cloud_ollama_variants_are_not_used_locally():
    found=installed_model_names({'models':[{'name':'qwen2.5-coder:7b'}, {'name':'qwen3-coder:480b-cloud'}, {'name':'x:cloud'}]})
    assert found==['qwen2.5-coder:7b']


def test_coding_rank_prefers_specialist_over_general():
    assert coding_rank('qwen2.5-coder:7b')>coding_rank('deepseek-coder:6.7b')>coding_rank('qwen3:4b')


@pytest.mark.asyncio
async def test_auto_plan_picks_installed_specialist_before_general(tmp_path, monkeypatch):
    config=Config.model_validate({'providers':[
        {'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1','priority':12,'requires_key':False,
         'models':[{'name':'qwen3:4b','strengths':['coding'],'context_window':32768},
                   {'name':'deepseek-coder:6.7b','strengths':['coding'],'context_window':32768},
                   {'name':'qwen2.5-coder:7b','strengths':['coding'],'context_window':32768}]}
    ]})
    eng=Engine(config,cache_path=str(tmp_path/'cache.db'))
    eng.refresh_local=AsyncMock(return_value=config.providers[0])
    calls=[]
    async def fake_complete(provider,model,messages):
        calls.append(model.name)
        return '{"steps":[{"tool":"workspace_read","args":{"path":"main.py"}}]}'
    monkeypatch.setattr('router.engine.complete',fake_complete)
    def validate(plan):
        assert json.loads(plan)['steps']
    result=await eng.run([{'role':'user','content':'ابني تطبيق'}],model='auto',task_hint='coding',response_validator=validate,use_cache=False)
    assert calls==['qwen2.5-coder:7b']
    assert result['offline'] is True


@pytest.mark.asyncio
async def test_cloud_only_never_calls_ollama(tmp_path,monkeypatch):
    config=Config.model_validate({'providers':[
        {'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1','models':[{'name':'qwen2.5-coder:7b','strengths':['coding'],'context_window':32768}]},
        {'name':'groq','base_url':'https://api.groq.com/openai/v1','api_key_env':'FREE_TEST_KEY',
         'models':[{'name':'fake','strengths':['coding'],'context_window':32768}]}
    ]})
    monkeypatch.setenv('FREE_TEST_KEY','test')
    eng=Engine(config,cache_path=str(tmp_path/'cache.db'))
    eng.routing_mode='cloud'
    eng.refresh_local=AsyncMock()
    seen=[]
    async def fake_complete(provider,model,messages):
        seen.append(provider.name)
        return '{"steps":[{"tool":"workspace_read","args":{"path":"main.py"}}]}'
    monkeypatch.setattr('router.engine.complete',fake_complete)
    result=await eng.run([{'role':'user','content':'build code'}],task_hint='coding',response_validator=lambda x:json.loads(x),use_cache=False)
    assert seen==['groq']
    eng.refresh_local.assert_not_called()
    assert result['offline'] is False
