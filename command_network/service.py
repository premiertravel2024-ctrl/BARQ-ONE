"""Network facade for the existing BARQ Engine and its approval-safe Brain."""
from __future__ import annotations
import time
from .contracts import Request,Event
from .triage import Triage
from .registry import Registry
from .routing import DecisionRouter
from .control import CircuitBreaker,Quota
from .cache import ExactCache
from .semantic_cache import SemanticCache
from .trace import TraceStore
from .verifier import verify

class CommandNetwork:
    def __init__(self,engine):
        self.engine=engine
        self.triage=Triage();self.registry=Registry(engine.config)
        self.router=DecisionRouter();self.breaker=CircuitBreaker()
        self.quota=engine.limiter;self.cache=ExactCache();self.semantic=SemanticCache();self.trace=TraceStore()
    def prepare(self,request:Request,*,task_hint=None,prompt_contract=False):
        start=time.perf_counter();self.trace.start(request.request_id)
        profile=self.triage.classify(request)
        if task_hint in ('simple','coding','reasoning') and prompt_contract and all(isinstance(m.get('content'),str) for m in request.messages):
            # This is an application-owned text classification/tool-plan call.
            # JSON/image/tool words in the *specification* are data, not native
            # API capabilities required to interpret it. The caller validates
            # the text contract and can fall through to another text model.
            profile=profile.model_copy(update={'task_type':'chat' if task_hint=='simple' else task_hint,
                'domain':'software' if task_hint=='coding' else profile.domain,
                'difficulty':'hard' if task_hint=='coding' else 'medium',
                'needs_json':False,'requires_native_json':False,'needs_tools':False,'requires_native_tool_calls':False,
                'modality':'text','layer':'application_contract'})
        if self.triage.privacy_required(request) and request.privacy=='normal':
            request=request.model_copy(update={'privacy':'local-only'})
            self.trace.span(request.request_id,'privacy',reason='sensitive input; forced local-only')
        self.trace.span(request.request_id,'triage',task_type=profile.task_type,duration_ms=round((time.perf_counter()-start)*1000,2))
        plan=self.router.plan(request,profile,self.registry.list(),health=self.engine.health,quota=self.quota,breaker=self.breaker,recent_provider=self.engine._recent_cloud_provider)
        self.trace.span(request.request_id,'route',model=plan.chain[0] if plan.chain else None,reason=plan.reason,strategy=plan.strategy)
        return request,plan
    def order_existing(self,request,prepared,profile,plan):
        # The old Router already enforces secrets/health/quotas. Never add
        # candidates not present in that original allowlisted output.
        keys={p.name+'/'+m.name:(p,m) for p,m in prepared}
        return [keys[k] for k in plan.chain if k in keys]
    async def handle(self,request:Request):
        """High-level typed event iterator. Existing engine performs calls, not this interface."""
        req,plan=self.prepare(request)
        rid=req.request_id
        yield Event(type='routing',request_id=rid,data={'plan':plan.model_dump()})
        if not plan.chain:
            self.trace.span(rid,'error',status='no eligible model')
            yield Event(type='error',request_id=rid,data={'reason':'No eligible model. Check privacy, model keys and required capabilities.'})
            return
        if req.privacy=='local-only' and not any(s.startswith('ollama/') for s in plan.chain):
            self.trace.span(rid,'error',status='no local model')
            yield Event(type='error',request_id=rid,data={'reason':'Install an Ollama model for local-only requests.'})
            return
        start=time.perf_counter()
        try:
            # Do not execute tools here; all actions must go through agent permission flow.
            result=await self.engine.run(req.messages,model=req.model,use_cache=False,network_mode=req.mode,privacy=req.privacy,network_request_id=rid)
            check=verify(result['content'],plan.profile)
            self.trace.span(rid,'verify',result=check.reason,confidence=check.confidence)
            self.engine.health.feedback(result['model'],check.accepted)
            self.trace.span(rid,'final',model=result['model'],duration_ms=round((time.perf_counter()-start)*1000,1))
            yield Event(type='verified',request_id=rid,data={'confidence':check.confidence,'passed':check.accepted})
            yield Event(type='final',request_id=rid,data={'content':result['content'],'model':result['model'],'confidence':check.confidence,'route':plan.chain,'attempts':result.get('attempts',[])})
        except Exception as exc:
            self.trace.span(rid,'error',status=type(exc).__name__)
            yield Event(type='error',request_id=rid,data={'reason':type(exc).__name__})
    def map(self):
        return {'models':[{'id':m.id,'provider':m.provider,'enabled':m.enabled,'configured':m.configured,
                           'health':'red' if not self.engine.health.available(m.id) else 'green' if m.configured and self.engine.health.data[m.id]['ok']>0 else 'amber',
                           'local':m.kind=='local','remaining_today':self.engine.limiter.remaining(m.provider if m.provider in ('openrouter','cloudflare') else m.id,m.rpd)}
                          for m in self.registry.list()],
                'traces':self.trace.recent(12), 'metrics':self.trace.metrics()}
