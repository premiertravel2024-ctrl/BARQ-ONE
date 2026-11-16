"""v2.9 free-only, offline security and deterministic quota regressions."""
from pathlib import Path
import copy,os
import httpx,pytest,yaml
from fastapi.testclient import TestClient
from router.free_policy import permitted,blocked,set_block,note_billing
from router.config import load_config,Config,merge_new_builtin_providers
from router.quota import QuotaManager,quota_key


def test_bundled_models_cannot_route_paid_and_unknown():
    cfg=load_config()
    for provider in cfg.providers:
        for model in provider.models:
            if provider.kind=='cloud' and model.enabled:
                assert model.free and permitted(provider.name,model.name)
    assert not permitted('cloudflare','@cf/zai-org/glm-5.3')
    assert not permitted('openrouter','deepseek/deepseek-v4.1')


def test_explicit_paid_model_rejected():
    with pytest.raises(ValueError,match='Cloud model not approved'):
        Config.model_validate({'providers':[{'name':'groq','base_url':'https://api.groq.com/openai/v1',
                                            'models':[{'name':'paid-upstream','free':True}]}]})


def test_402_blocks_persistently_but_429_is_not_billing(monkeypatch,tmp_path):
    monkeypatch.setattr('core.paths.data_dir',lambda:tmp_path)
    assert note_billing('groq',429,'rate limit exceeded') is False
    assert not blocked('groq')
    assert note_billing('groq',402,'Payment Required') is True
    assert blocked('groq')
    assert not next(p for p in load_config().providers if p.name=='groq').enabled
    assert note_billing('nvidia',400,'insufficient credits') is True
    assert blocked('nvidia')
    set_block('groq',False);set_block('nvidia',False)


def test_old_preferences_migrate_without_losing_priority(monkeypatch,tmp_path):
    monkeypatch.setattr('core.paths.data_dir',lambda:tmp_path)
    original={'providers':[{'name':'groq','base_url':'https://api.groq.com/openai/v1',
                           'api_key_env':'GROQ_API_KEY','enabled':False,'priority':27,
                           'rpm':3,'models':[{'name':'openai/gpt-oss-120b','strengths':['coding'],
                                               'context_window':12000}, {'name':'groq/paid-model'}]}]}
    p=tmp_path/'providers.yaml';p.write_text(yaml.safe_dump(original),encoding='utf-8')
    cfg=load_config()
    prov=next(x for x in cfg.providers if x.name=='groq')
    assert prov.priority==27 and not prov.enabled and prov.rpm==3
    assert next(m for m in prov.models if m.name=='groq/paid-model').enabled is False
    assert next(m for m in prov.models if m.name=='openai/gpt-oss-120b').free is True
    assert (tmp_path/'providers.yaml.bak').exists()
    assert next(x for x in cfg.providers if x.name=='nvidia')


def test_quota_model_isolation_and_tpm_with_fake_clock():
    t=[1234567.]
    q=QuotaManager(clock=lambda:t[0],margin=0)
    q.record('groq/one',estimated_tokens=850)
    assert not q.allowed('groq/one',rpm=10,tpm=1000,expected_tokens=151)
    assert q.allowed('groq/two',rpm=10,tpm=1000,expected_tokens=151)
    t[0]+=61
    assert q.allowed('groq/one',rpm=10,tpm=1000,expected_tokens=151)


def test_quota_account_scope_and_sqlite_restart(tmp_path):
    now=[1234567.]
    path=tmp_path/'usage.sqlite3'
    a=QuotaManager(clock=lambda:now[0],margin=0,db_path=path)
    a.record('openrouter',estimated_tokens=20)
    b=QuotaManager(clock=lambda:now[0],margin=0,db_path=path)
    assert not b.allowed('openrouter',rpm=1)
    assert b.remaining('openrouter',3)==2


def test_bundle_host_pinning_defends_against_edited_user_config(monkeypatch,tmp_path):
    monkeypatch.setattr('core.paths.data_dir',lambda:tmp_path)
    original=yaml.safe_load(Path('config/providers.yaml').read_text(encoding='utf-8'))
    original['providers'][0]['base_url']='https://malicious.invalid/v1'
    (tmp_path/'providers.yaml').write_text(yaml.safe_dump(original),encoding='utf-8')
    # Migration pins back to trusted bundled host. No key goes to edited host.
    cfg=load_config()
    assert next(p for p in cfg.providers if p.name=='gemini').base_url.startswith('https://generativelanguage.googleapis.com')


def test_free_audit_offline_and_no_secrets(monkeypatch):
    import api
    secret='v29_secret_CANNOT_LEAK'
    monkeypatch.setenv('NVIDIA_API_KEY',secret)
    with TestClient(api.app) as client:
        r=client.get('/v1/free-audit')
    assert r.status_code==200
    assert secret not in r.text
    assert r.json()['providers'] and 'warnings' in r.json()
    assert 'billing_blocked' in r.json()['providers'][0]


def test_paid_checkout_billing_urls_not_called_from_source():
    # Static guard for newly introduced payment actions. Don't ban words in warnings.
    import ast
    for module in (Path('router'),Path('providers'),Path('command_network')):
        for path in module.glob('*.py'):
            root=ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(root):
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.startswith(('https://','http://')):
                    assert not any(part in node.value.lower() for part in ('/checkout','/purchase','/billing/upgrade','/buy-credits'))
