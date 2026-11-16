"""Local model health and bounded feedback EMA; no prompts or credentials stored."""
import json,time
from pathlib import Path
from collections import defaultdict
class Health:
    def __init__(self,path=None):
        self.path=Path(path) if path else None
        self.data=defaultdict(lambda:{'ok':0,'fail':0,'latency':0.0,'ttft':0.0,'cooldown':0.0,'quality_delta':0.0,'output_quality':1.0,'task_outcomes':{},'verified_outcomes':{}})
        if self.path and self.path.exists():
            try:
                data=json.loads(self.path.read_text(encoding='utf-8'))
                for key,v in data.items():
                    if isinstance(key,str) and isinstance(v,dict) and len(key)<180:
                        self.data[key].update({f:v[f] for f in ('ok','fail','latency','ttft','cooldown','quality_delta','output_quality')
                                                 if f in v and isinstance(v[f],(int,float))})
                        if isinstance(v.get('verified_outcomes'),dict):
                            for task,record in v['verified_outcomes'].items():
                                if (isinstance(task,str) and len(task)<40 and isinstance(record,dict)
                                        and all(isinstance(record.get(k),(int,float)) for k in ('ok','fail'))):
                                    self.data[key].setdefault('verified_outcomes',{})[task]={
                                        'ok':min(10000,max(0,int(record['ok']))),'fail':min(10000,max(0,int(record['fail'])))}
                        if isinstance(v.get('task_outcomes'),dict):
                            for task,record in v['task_outcomes'].items():
                                if (isinstance(task,str) and len(task)<40 and isinstance(record,dict)
                                        and all(isinstance(record.get(k), (int,float)) for k in ('ok','fail','latency'))):
                                    self.data[key]['task_outcomes'][task]={'ok':min(10000,max(0,int(record['ok']))),
                                        'fail':min(10000,max(0,int(record['fail']))),
                                        'latency':max(0.,min(120.,float(record['latency'])))}
            except (OSError,ValueError):pass
    def _save(self):
        if not self.path:return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(dict(self.data),ensure_ascii=False),encoding='utf-8')
        tmp.replace(self.path)
    def available(self,key):return self.data[key]['cooldown']<=time.time()
    def report(self,key,ok,latency=0,cooldown=0,ttft=None,task=None):
        d=self.data[key];d['ok' if ok else 'fail']+=1
        if ok:
            d['cooldown']=0.0
            d['latency']=latency if not d['latency'] else .7*d['latency']+.3*latency
            if ttft is not None:d['ttft']=ttft if not d['ttft'] else .7*d['ttft']+.3*ttft
        if cooldown:d['cooldown']=time.time()+cooldown
        # Task-specific outcomes use only model IDs, category, duration, and outcome.
        # Never store prompts or file paths. At least four samples are required
        # before this evidence may affect model ranking.
        if isinstance(task,str) and 0 < len(task) <= 40:
            records=d.setdefault('task_outcomes',{})
            record=records.setdefault(task,{'ok':0,'fail':0,'latency':0.0})
            record['ok' if ok else 'fail']+=1
            if ok and latency>=0:
                record['latency']=float(latency) if not record['latency'] else round(.75*record['latency']+.25*latency,4)
        self._save()
    def report_quality(self,key,valid):
        """Track model-format reliability without poisoning provider availability."""
        d=self.data[key]
        previous=float(d.get('output_quality',1.0))
        d['output_quality']=round(.8*previous+.2*(1.0 if valid else 0.0),5)
        self._save()

    def report_task_result(self,key,task,success):
        """Record real approved verification/build result, not model output."""
        if not isinstance(task,str) or not task or len(task)>40:return
        if not isinstance(key,str) or '/' not in key or len(key)>180:return
        d=self.data[key];record=d.setdefault('verified_outcomes',{}).setdefault(task,{'ok':0,'fail':0})
        record['ok' if success else 'fail']=min(10000,record['ok' if success else 'fail']+1)
        self._save()

    def task_adjustment(self,key,task):
        """Conservative trace-derived routing (OpenJarvis-inspired).

        Sparse observations can't override hardware/capability selection.
        A smoothed prior avoids routing one bad outcome into a blacklist.
        """
        record=self.data[key].get('task_outcomes',{}).get(task,{})
        ok=max(0,int(record.get('ok',0)));fail=max(0,int(record.get('fail',0)))
        total=ok+fail
        success=(ok+2)/(total+4)
        inferred=(max(-9.0,min(9.0,(success-.5)*18*min(1.,total/12)))
                  if total>=4 else 0.0)
        verification=self.data[key].get('verified_outcomes',{}).get(task,{})
        verified_ok=max(0,int(verification.get('ok',0)));verified_fail=max(0,int(verification.get('fail',0)))
        verified_total=verified_ok+verified_fail
        if total<4 and verified_total<2:return 0.0
        if verified_total>=2:
            verified_success=(verified_ok+1)/(verified_total+2)
            inferred+=max(-7.,min(7.,(verified_success-.5)*14*min(1.,verified_total/8)))
        return round(max(-12.,min(12.,inferred)),4)

    def feedback(self,key,positive):
        """One user action changes the quality calibration by at most .01."""
        d=self.data[key]
        current=float(d.get('quality_delta',0))
        target=.1 if positive else -.1
        d['quality_delta']=max(-.1,min(.1,round(.9*current+.1*target,5)))
        self._save()
        return d['quality_delta']
    def quality_adjustment(self,key):return float(self.data[key].get('quality_delta',0))
    def reset_feedback(self,key=None):
        for k in ([key] if key else list(self.data)):
            self.data[k]['quality_delta']=0.
        self._save()
    def snapshot(self):return dict(self.data)
