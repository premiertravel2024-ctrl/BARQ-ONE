"""Local redacted trace records; never save message contents or tokens."""
from __future__ import annotations
from collections import deque,defaultdict
import asyncio,time,uuid

class TraceStore:
    def __init__(self,maxlen=200):self.traces={};self.order=deque(maxlen=maxlen);self.lock=asyncio.Lock()
    def start(self,request_id=None):
        rid=request_id or uuid.uuid4().hex
        if rid not in self.traces:
            if len(self.order)==self.order.maxlen:self.traces.pop(self.order[0],None)
            self.order.append(rid);self.traces[rid]={'id':rid,'created':time.time(),'steps':[],'model':None,'status':'running'}
        return rid
    def span(self,rid,stage,**data):
        item=self.traces.get(rid)
        if not item:return
        allowed={'duration_ms','model','provider','strategy','task_type','result','fallbacks','cache_hit','status','reason','confidence'}
        sanitized={k:v for k,v in data.items() if k in allowed and isinstance(v,(int,float,bool,str,type(None)))}
        item['steps'].append({'stage':stage,'ts':time.time(),**sanitized})
        if stage=='final':item['model']=data.get('model');item['status']='done'
        if stage=='error':item['status']='error'
    def get(self,rid):return self.traces.get(rid)
    def recent(self,limit=15):return [self.traces[rid] for rid in list(self.order)[-min(50,limit):][::-1]]
    def metrics(self):
        completed=[x for x in self.traces.values() if x['status']=='done']
        by_stage=defaultdict(list)
        for x in self.traces.values():
            for stage in x['steps']:
                if 'duration_ms' in stage:by_stage[stage['stage']].append(stage['duration_ms'])
        def pct(values,p):
            if not values:return None
            v=sorted(values);return round(v[min(len(v)-1,int((len(v)-1)*p))],1)
        return {'requests':len(self.traces),'completed':len(completed),'latency_ms':{k:{'p50':pct(v,.5),'p95':pct(v,.95)} for k,v in by_stage.items()}}
