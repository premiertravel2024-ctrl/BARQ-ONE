"""Safe provider configuration: bundled immutable trust + migratable user choices."""
from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel,Field,model_validator
from dotenv import load_dotenv
load_dotenv()

class Model(BaseModel):
    name:str
    strengths:list[str]=Field(default_factory=list)
    context_window:int=8192
    enabled:bool=True
    free:bool=False
    data_use:Literal['no-training','may-train','unknown']='unknown'
    retires:str|None=None
    rpm:int=0
    rpd:int=0
    tpm:int=0
    tpd:int=0
    max_concurrent:int=0
    max_input_tokens:int=0

class Provider(BaseModel):
    name:str
    base_url:str
    kind:Literal['cloud','local']='cloud'
    api_key_env:str|None=None
    enabled:bool=True
    priority:int=Field(default=50,ge=0,le=100)
    rpm:int=0
    rpd:int=0
    tpm:int=0
    tpd:int=0
    max_concurrent:int=0
    quota_scope:Literal['model','provider','account']='model'
    free_status:Literal['free','conditional','requires_payment_method','unverified']='unverified'
    data_use:Literal['no-training','may-train','unknown']='unknown'
    notes_ar:str=''
    disabled_reason_ar:str=''
    requires_key:bool=True
    models:list[Model]
    @model_validator(mode='after')
    def validate_free(self):
        from router.free_policy import permitted,blocked
        if self.kind=='local':
            from providers.ollama import verified_base_url
            if self.name!='ollama':raise ValueError('Only verified local Ollama supported')
            self.base_url=verified_base_url(self.base_url)
            if self.api_key_env:raise ValueError('Local Ollama must not require cloud keys')
            return self
        from router.config import bundled_providers
        bundled=bundled_providers().get(self.name)
        # Directly injected test configurations are permitted for offline fakes.
        # Actual runtime configs are separately pinned in load_config() and HTTP adapters.
        if bundled is None:return self
        if self.free_status=='requires_payment_method' or self.name=='cerebras':
            if self.enabled:raise ValueError('Provider requires a payment method and cannot be enabled')
        if blocked(self.name) and self.enabled:raise ValueError('Billing-blocked provider cannot be enabled')
        for model in self.models:
            if self.name=='openrouter' and not (model.name=='openrouter/free' or model.name.endswith(':free')):
                raise ValueError('OpenRouter paid model blocked: '+model.name)
            if 'free' not in model.model_fields_set and permitted(self.name,model.name):
                model.free=True  # backward-compatible constructor; persisted data migrates explicitly
            if model.enabled and 'free' in model.model_fields_set and not (model.free and permitted(self.name,model.name)):
                raise ValueError('Cloud model not approved for free routing: '+model.name)
            if model.retires:
                try:
                    if date.fromisoformat(model.retires)<=date.today():model.enabled=False
                except ValueError:raise ValueError('Invalid model retirement date')
        return self

class Config(BaseModel):
    catalog_version:int=1
    providers:list[Provider]


def _builtin():
    from core.paths import resource
    return yaml.safe_load(resource('config','providers.yaml').read_text(encoding='utf-8'))

def bundled_providers():
    return {p['name']:p for p in _builtin().get('providers',[])}

def _copy(value):
    import copy
    return copy.deepcopy(value)

def merge_new_builtin_providers(data):
    """Migrate user state, never overwrite existing user priorities, quotas or enabled flags."""
    from router.free_policy import permitted,blocked
    default=_builtin()
    if not isinstance(data,dict) or not isinstance(data.get('providers'),list):return data
    old=int(data.get('catalog_version',0) or 0)
    version=int(default.get('catalog_version',1))
    built={p['name']:p for p in default['providers']}
    for item in data['providers']:
        if not isinstance(item,dict):continue
        bp=built.get(item.get('name'))
        if not bp:
            item['enabled']=False
            continue
        # Endpoints and secret names are trust configuration, not user settings.
        for field in ('base_url','api_key_env','kind','free_status','data_use','notes_ar','requires_key','quota_scope'):
            if field in bp:item[field]=_copy(bp[field])
        by_name={m['name']:m for m in bp.get('models',[])}
        for m in item.get('models',[]):
            if not isinstance(m,dict):continue
            bm=by_name.get(m.get('name'))
            if bm:
                for f,val in bm.items():m.setdefault(f,_copy(val))
            if not permitted(item['name'],m.get('name','')) or not (bm and bm.get('free')) or m.get('free') is False:
                m['enabled']=False;m['free']=False
            else:m['free']=True
        present={m.get('name') for m in item.get('models',[]) if isinstance(m,dict)}
        for bm in bp.get('models',[]):
            if bm['name'] not in present:item.setdefault('models',[]).append(_copy(bm))
        if bp.get('free_status')=='requires_payment_method' or blocked(item['name']):item['enabled']=False
    present={p.get('name') for p in data['providers'] if isinstance(p,dict)}
    for name,p in built.items():
        if name not in present:data['providers'].append(_copy(p))
    data['catalog_version']=max(version,old)
    return data


def load_config(path=None):
    from core.paths import resource,state_file
    user=state_file('providers.yaml')
    is_user=path is None and user.exists()
    target=Path(path) if path else (user if is_user else resource('config','providers.yaml'))
    data=yaml.safe_load(target.read_text(encoding='utf-8'))
    if is_user:
        initial=int(data.get('catalog_version',0) or 0) if isinstance(data,dict) else 0
        data=merge_new_builtin_providers(data)
        if int(data.get('catalog_version',0))>initial:
            backup=user.with_name('providers.yaml.bak')
            if not backup.exists():backup.write_bytes(user.read_bytes())
            # Atomic state migration; keys remain in OS credential service.
            tmp=user.with_suffix('.tmp');tmp.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8');tmp.replace(user)
    # A provider blocked after a billing error must not break the next startup.
    from router.free_policy import blocked
    for provider_data in data.get('providers',[]):
        if blocked(provider_data.get('name','')):provider_data['enabled']=False
    # Runtime files must satisfy the bundled, immutable free policy. Direct
    # Config.model_validate calls remain usable for isolated fake-provider tests.
    from router.free_policy import permitted
    if isinstance(data,dict):
        trusted=bundled_providers()
        for item in data.get('providers',[]):
            bp=trusted.get(item.get('name'))
            if not bp:
                if item.get('enabled'):raise ValueError('Unknown enabled cloud provider')
                continue
            if item.get('base_url')!=bp.get('base_url') or item.get('api_key_env')!=bp.get('api_key_env'):
                raise ValueError('Untrusted endpoint or API credential variable')
            if item.get('kind','cloud')=='cloud':
                for model in item.get('models',[]):
                    if model.get('enabled',True) and not (model.get('free',False) and permitted(item['name'],model.get('name',''))):
                        raise ValueError('Paid/unverified cloud model blocked: '+str(model.get('name')))
    return Config.model_validate(data)

def key_for(p):
    from core.secrets import get
    from router.free_policy import blocked
    if p.kind=='local':return 'local-no-key-required'
    if blocked(p.name):return ''
    return get(p.api_key_env) if p.api_key_env else ('keyless' if not p.requires_key else '')
