"""Capability-aware routing; no network calls or tool permissions are granted here."""
from __future__ import annotations
import random
from pathlib import Path
import yaml
from .contracts import Request,TaskProfile,RoutePlan
from .registry import Capability

DEFAULT_WEIGHTS={'fast':(.20,.50,.14,.16),'balanced':(.48,.22,.13,.17),'best':(.69,.08,.08,.15)}
class DecisionRouter:
    def __init__(self,policy_file=None,random_source=None):
        self.path=Path(policy_file) if policy_file else Path(__file__).resolve().parents[1]/'config'/'policies.yaml'
        self.stamp=None;self.settings={};self.random=random_source or random.random
    def policy(self):
        try:stamp=self.path.stat().st_mtime_ns
        except OSError:stamp=None
        if stamp!=self.stamp:
            self.stamp=stamp
            try:self.settings=yaml.safe_load(self.path.read_text(encoding='utf-8')) or {}
            except (OSError,ValueError,yaml.YAMLError):self.settings={}
        return self.settings
    def plan(self,req:Request,profile:TaskProfile,models:list[Capability],health=None,quota=None,breaker=None,recent_provider=None):
        cfg=self.policy();weights=cfg.get('mode_weights',{}).get(req.mode,{})
        if isinstance(weights,dict):w=tuple(float(weights.get(k,d)) for k,d in zip(('quality','latency','availability','reliability'),DEFAULT_WEIGHTS[req.mode]))
        else:w=DEFAULT_WEIGHTS[req.mode]
        rejected={}; scores={}; surviving=[]
        local_only=req.privacy=='local-only'
        for m in models:
            reason=None
            if not m.enabled or m.draining:reason='disabled or draining'
            elif not m.configured:reason='missing provider credentials or local model'
            elif local_only and m.kind!='local':reason='privacy: local-only'
            elif profile.modality=='image' and 'image' not in m.modalities:reason='image input unsupported'
            elif profile.requires_native_json and not m.supports_json:reason='native structured JSON unsupported'
            elif profile.requires_native_tool_calls and not m.supports_tools:reason='native tool calls unsupported'
            elif m.max_input_tokens and profile.token_estimate>m.max_input_tokens:reason='input token budget exceeded'
            elif profile.token_estimate+512>m.context_window:reason='insufficient context'
            elif breaker and not (breaker.peek(m.id) if hasattr(breaker,'peek') else breaker.allowed(m.id)):reason='circuit breaker open'
            elif health and not health.available(m.id):reason='existing health circuit open'
            elif quota and not quota.allowed(m.quota_key or m.id,m.rpm,m.rpd,m.tpm,profile.token_estimate,m.tpd):reason='quota exhausted'
            if reason:
                rejected[m.id]=reason;continue
            signal=health.data[m.id] if health else None
            latency=(signal or {}).get('latency',m.p50_latency) or m.p50_latency
            reliability=(signal or {}).get('ok',0);failure=(signal or {}).get('fail',0)
            reliability=(reliability+2)/(reliability+failure+4) if health and (reliability or failure) else m.reliability
            speed=1/(1+max(.02,float(latency))/2)
            availability=1.0 if not m.rpd else max(.1,min(1.,.7)) # unknown quota use conservative neutral value
            quality=m.quality(profile.task_type)
            if profile.language in ('ar','mixed'):quality=.82*quality+.18*m.arabic_quality
            score=w[0]*quality+w[1]*speed+w[2]*availability+w[3]*reliability
            if health and hasattr(health,'quality_adjustment'):score+=health.quality_adjustment(m.id)
            if m.pinned:score+=.08
            # Avoid sticky providers on ordinary requests; user-pinned and hard tasks are unaffected.
            if recent_provider and m.provider==recent_provider and not m.pinned and profile.difficulty!='hard':score-=.22
            scores[m.id]=round(score,5)
            surviving.append((score,m))
        surviving.sort(key=lambda item:item[0],reverse=True)
        # Exploratory routing happens only for low-risk, non-private tasks; never hides provider choice.
        # Avoid cold-start random routing before there is enough real evidence.
        observations=sum(health.data[m.id]['ok']+health.data[m.id]['fail'] for _,m in surviving) if health else 0
        if len(surviving)>1 and observations>=20 and profile.risk=='low' and profile.difficulty!='hard' and not local_only:
            if self.random()<float(cfg.get('exploration_rate',.05)):
                close=[i for i,entry in enumerate(surviving[1:],start=1) if surviving[0][0]-entry[0]<.08]
                if close:
                    idx=close[0];surviving[0],surviving[idx]=surviving[idx],surviving[0]
        # Provider diversity, and offline Ollama only at end unless local-only.
        cloud=[m for _,m in surviving if m.kind!='local']
        local=[m for _,m in surviving if m.kind=='local']
        result=[];last_provider=None
        while cloud:
            idx=next((i for i,m in enumerate(cloud) if m.provider!=last_provider),0)
            item=cloud.pop(idx);result.append(item.id);last_provider=item.provider
        # Local fallback is always last: never interleave Ollama between cloud models.
        result.extend(m.id for m in local)
        # explicit user model is never changed silently
        if req.model not in ('auto','local-only'):
            chosen=[m for m in result if m==req.model or m.split('/',1)[-1]==req.model]
            result=chosen
        result=result[:max(1,min(int(cfg.get('max_models_per_request',5)),10))]
        smart=profile.difficulty=='hard' or profile.needs_long_context or profile.needs_tools
        strategy='plan_execute' if profile.needs_tools and smart else 'map_reduce' if profile.needs_long_context and smart else 'cascade' if smart else 'single'
        if req.mode=='fast' and not smart and len(result)>1 and profile.latency_sensitivity>.8:
            strategy='hedged' # plan only: runtime uses sequential safe fallback until hedging enabled
        reason=('مسار ذكي' if smart else 'مسار سريع')+'؛ '+('خصوصية محلية؛ ' if local_only else '')+('لا يوجد موديل مؤهل' if not result else 'الأولوية للقدرة على '+profile.task_type+' ثم السرعة والموثوقية؛ '+result[0])
        return RoutePlan(request_id=req.request_id,chain=result,strategy=strategy,smart_path=smart,reason=reason,rejected=rejected,scores=scores,
            timeouts={'total':req.deadline_seconds,'connect':8,'first_token':min(15,req.deadline_seconds/2)},profile=profile)
