"""Offline regression tests for the NVIDIA-hosted DeepSeek catalog integration."""
from pathlib import Path
import httpx
import pytest
from router.config import load_config, key_for
from providers.discovery import endpoint_for, validated_chat_url, CloudInspector
from command_network.registry import Registry


def test_nvidia_provider_and_model_are_shipped():
    cfg=load_config(Path(__file__).resolve().parents[1]/'config/providers.yaml')
    p=next(p for p in cfg.providers if p.name=='nvidia')
    assert p.api_key_env=='NVIDIA_API_KEY'
    assert p.base_url=='https://integrate.api.nvidia.com/v1'
    assert p.enabled
    assert 'deepseek-ai/deepseek-v4.1-flash' in [m.name for m in p.models]
    # v2.9 deliberately expands the catalog; suggested IDs remain disabled until verified.
    assert all(not m.enabled for m in p.models if m.name != 'deepseek-ai/deepseek-v4.1-flash')
    assert endpoint_for(p)=='https://integrate.api.nvidia.com/v1/models'
    assert validated_chat_url(p)=='https://integrate.api.nvidia.com/v1/chat/completions'


def test_nvidia_key_is_not_hardcoded(monkeypatch):
    from core import secrets
    monkeypatch.delenv('NVIDIA_API_KEY', raising=False)
    monkeypatch.setattr(secrets, 'get', lambda name: '' if name=='NVIDIA_API_KEY' else 'unexpected')
    cfg=load_config(Path(__file__).resolve().parents[1]/'config/providers.yaml')
    assert not key_for(next(p for p in cfg.providers if p.name=='nvidia'))
    assert 'NVIDIA_API_KEY' in Path(__file__).resolve().parents[1].joinpath('.env.example').read_text()


def test_nvidia_registry_supports_image_but_does_not_claim_native_tools(monkeypatch):
    from core import secrets
    monkeypatch.setattr(secrets,'get',lambda name:'test-key')
    cfg=load_config(Path(__file__).resolve().parents[1]/'config/providers.yaml')
    m=next(m for m in Registry(cfg).list() if m.id=='nvidia/deepseek-ai/deepseek-v4.1-flash')
    assert 'image' in m.modalities
    assert m.strengths['coding']>0.85
    assert m.supports_tools is False
    assert m.configured


@pytest.mark.asyncio
async def test_nvidia_discovery_and_transport_are_pinned(monkeypatch):
    from core import secrets
    monkeypatch.setattr(secrets,'get',lambda name:'fake-offline-token')
    cfg=load_config(Path(__file__).resolve().parents[1]/'config/providers.yaml')
    p=next(p for p in cfg.providers if p.name=='nvidia')
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json={'data':[{'id':'deepseek-ai/deepseek-v4.1-flash'}]})
    r=await CloudInspector().check(p,transport=httpx.MockTransport(handler))
    assert r['verified'] and r['models']==['deepseek-ai/deepseek-v4.1-flash']
    assert len(requests)==1
    assert requests[0].url.host=='integrate.api.nvidia.com'
    assert requests[0].headers['authorization']=='Bearer fake-offline-token'
    from router.config import Provider
    bad=Provider.model_validate({'name':'nvidia','base_url':'https://evil.example/v1','api_key_env':'NVIDIA_API_KEY','models':[{'name':'deepseek-ai/deepseek-v4.1-flash'}]})
    with pytest.raises(ValueError,match='Untrusted provider endpoint'):
        validated_chat_url(bad)


def test_frontend_supports_secret_entry():
    src=(Path(__file__).resolve().parents[1]/'frontend/src/components/workspace/ModelControls.tsx').read_text(encoding='utf-8')
    assert "nvidia:'NVIDIA_API_KEY'" in src
    assert 'https://build.nvidia.com/settings' in src
    assert 'localStorage' not in src


def test_existing_user_config_is_upgraded_without_erasing_preferences(monkeypatch,tmp_path):
    import yaml
    from router.config import load_config
    from core.models import set_provider
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    state=tmp_path/'providers.yaml'
    cfg=yaml.safe_load((Path(__file__).resolve().parents[1]/'config/providers.yaml').read_text(encoding='utf-8'))
    cfg['providers']=[p for p in cfg['providers'] if p['name']!='nvidia']
    next(p for p in cfg['providers'] if p['name']=='groq')['priority']=17
    state.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding='utf-8')
    loaded=load_config()
    assert len([p for p in loaded.providers if p.name=='nvidia'])==1
    assert next(p for p in loaded.providers if p.name=='groq').priority==17
    set_provider('nvidia',enabled=False)
    loaded2=load_config()
    assert not next(p for p in loaded2.providers if p.name=='nvidia').enabled
    assert next(p for p in loaded2.providers if p.name=='groq').priority==17
