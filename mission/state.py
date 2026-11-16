"""Atomic mission metadata persistence. No generated code or secrets are saved here."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATUSES={'pending','writing','written','verified','failed','needs_attention'}

def _now():return datetime.now(timezone.utc).isoformat()

def create(goal,workspace,kind,paths,call_budget=80):
    from coding.blocks import safe_path
    if not isinstance(goal,str) or not goal.strip():raise ValueError('Missing goal')
    if call_budget<1 or call_budget>500:raise ValueError('Invalid call budget')
    return {'id':uuid.uuid4().hex,'goal':goal,'workspace':str(workspace),'kind':kind,
            'status':'pending','created':_now(),'updated':_now(),
            'call_budget':call_budget,'calls_used':0,
            'manifest':[{'path':safe_path(path),'status':'pending','attempts':0,
                         'model_history':[],'last_error':'','hash':None} for path in paths]}

def next_item(mission):
    return next((item for item in mission['manifest'] if item['status'] not in ('verified','needs_attention')),None)

def report(mission):
    items=mission['manifest']; verified=sum(i['status']=='verified' for i in items)
    attention=sum(i['status']=='needs_attention' for i in items)
    return {'mission_id':mission['id'],'verified':verified,'needs_attention':attention,
            'remaining':len(items)-verified-attention,
            'complete':bool(items) and verified==len(items)}

class MissionStore:
    def __init__(self,root):self.root=Path(root)
    def _file(self,ident):
        if not isinstance(ident,str) or len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
            raise ValueError('Invalid mission id')
        return self.root/(ident+'.json')
    def save(self,mission):
        self.root.mkdir(parents=True,exist_ok=True)
        path=self._file(mission['id'])
        mission['updated']=_now()
        temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('x',encoding='utf-8') as f:
                json.dump(mission,f,ensure_ascii=False)
                f.flush();os.fsync(f.fileno())
            os.replace(temp,path)
        finally:
            temp.unlink(missing_ok=True)
    def load(self,ident):return json.loads(self._file(ident).read_text(encoding='utf-8'))
