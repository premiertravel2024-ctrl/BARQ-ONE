"""Capability registry derived from the existing safe provider configuration."""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel,Field
import yaml
from typing import Any

class Capability(BaseModel):
    id:str
    provider:str
    name:str
    kind:str='cloud'
    enabled:bool=True
    draining:bool=False
    pinned:bool=False
    configured:bool=True
    context_window:int=8192
    modalities:list[str]=Field(default_factory=lambda:['text'])
    supports_streaming:bool=True
    supports_json:bool=False
    supports_tools:bool=False
    rpm:int=0
    rpd:int=0
    tpm:int=0
    tpd:int=0
    max_input_tokens:int=0
    quota_scope:str="model"
    quota_key:str=""
    data_use:str="unknown"
    p50_latency:float=1.8
    p95_latency:float=7.0
    tokens_per_second:float=25
    reliability:float=.8
    arabic_quality:float=.6
    strengths:dict[str,float]=Field(default_factory=dict)
    privacy_note:str='Verify provider privacy terms for the chosen tier.'
    def quality(self,task):return self.strengths.get(task,.45)

STRENGTHS={'simple':'chat','fast':'chat','long-document':'long_document','vision':'vision','arabic':'qa','coding':'coding','reasoning':'reasoning','writing':'writing','translation':'translation'}
class Registry:
    def __init__(self,provider_config,overrides_file=None):
        self.provider_config=provider_config
        self.overrides_file=Path(overrides_file) if overrides_file else Path(__file__).resolve().parents[1]/'config'/'models.yaml'
        self._stamp=None
        self._overrides={}
    def _read_overrides(self):
        try:stamp=self.overrides_file.stat().st_mtime_ns
        except OSError:stamp=None
        if stamp!=self._stamp:
            self._stamp=stamp
            try:
                data=yaml.safe_load(self.overrides_file.read_text(encoding='utf-8')) or {}
                self._overrides=data.get('models',{})
            except (OSError,ValueError,yaml.YAMLError):self._overrides={}
        return self._overrides
    def list(self):
        from router.config import key_for
        overrides=self._read_overrides()
        result=[]
        for provider in self.provider_config.providers:
            for model in provider.models:
                ident=provider.name+'/'+model.name
                strength={label:.9 for original,label in STRENGTHS.items() if original in model.strengths}
                strength.update({tag:.9 for tag in model.strengths if tag not in STRENGTHS})
                default={'id':ident,'provider':provider.name,'name':model.name,'kind':provider.kind,
                         'enabled':provider.enabled and model.enabled,'configured':bool(key_for(provider)),'context_window':model.context_window,
                         'rpm':model.rpm or provider.rpm,'rpd':model.rpd or provider.rpd,
                         'tpm':model.tpm or provider.tpm,'tpd':model.tpd or provider.tpd,
                         'max_input_tokens':model.max_input_tokens,'data_use':model.data_use,
                         'quota_scope':provider.quota_scope,
                         'quota_key':provider.name if provider.quota_scope in ('provider','account') else ident,
                         'strengths':strength,
                         'arabic_quality':.85 if 'arabic' in model.strengths else .57,
                         'modalities':['text','image'] if 'vision' in model.strengths else ['text']}
                override=overrides.get(ident,{})
                if not isinstance(override,dict):override={}
                # Cannot turn an unconfigured cloud model into a configured one by overriding YAML.
                override={k:v for k,v in override.items() if k not in {'id','provider','name','kind','configured','enabled','quota_key','data_use'}}
                result.append(Capability.model_validate({**default,**override}))
        return result
