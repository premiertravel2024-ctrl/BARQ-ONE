from router.config import key_for
from router.free_policy import permitted,blocked
from router.quota import quota_key,estimate_tokens
class Router:
    def __init__(self,config,limiter,health,local_only=False):
        self.config,self.limiter,self.health,self.local_only=config,limiter,health,local_only
    def candidates(self,task,difficulty,chars=0,recent_provider=None):
        items=[]
        for p in self.config.providers:
            if not p.enabled or blocked(p.name) or (self.local_only and p.kind != 'local') or not key_for(p):continue
            for m in p.models:
                k=p.name+'/'+m.name
                if not m.enabled or (p.kind!='local' and 'free' in m.model_fields_set and not (m.free and permitted(p.name,m.name))):continue
                amount=estimate_tokens('x'*chars)+512
                if m.max_input_tokens and amount>m.max_input_tokens:continue
                if not self.health.available(k) or not self.limiter.allowed(quota_key(p,m) if 'free' in m.model_fields_set else p.name,m.rpm or p.rpm,m.rpd or p.rpd,m.tpm or p.tpm,amount,m.tpd or p.tpd):continue
                if chars//3+1024>m.context_window:continue
                d=self.health.data[k]
                reliability=(d['ok']+1)/(d['ok']+d['fail']+2)
                score=p.priority+35*(task in m.strengths)+15*reliability- min(20,d['latency'])
                # Evidence is learned per task type, not transferred between
                # unrelated skills. Cold-start candidates stay neutral.
                if hasattr(self.health,'task_adjustment'):
                    score += self.health.task_adjustment(k,task)
                # Once measured, time to first token matters for perceived speed.
                score -= min(18, 3.0 * d.get('ttft', 0.0))
                if difficulty=='hard' and ('reasoning' in m.strengths or 'coding' in m.strengths):score+=10
                if task=='coding':
                    # Higher coding quality wins over generic provider priority.
                    # These are local heuristics, not a benchmark or model guarantee.
                    score += 42 if 'coding' in m.strengths else -38
                    name=m.name.lower()
                    from command_network.routing import DecisionRouter
                    if any(tag in name for tag in DecisionRouter().policy().get('coding_name_boost',[])):
                        score += 12
                # Modest preference for a different equally-capable cloud provider.
                # Task strengths still outweigh this diversity adjustment.
                if recent_provider and p.kind != 'local' and p.name == recent_provider:
                    score -= 9
                items.append((score,p,m))
        return [(p,m) for _,p,m in sorted(items,key=lambda x:x[0],reverse=True)]
