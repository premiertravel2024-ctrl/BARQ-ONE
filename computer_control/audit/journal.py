"""Local append-only task audit. File contains no screenshots or secrets by default."""
from pathlib import Path
import hashlib,json,threading,time
from core.paths import data_dir
from computer_control.safety.policy import redact
_lock=threading.Lock()
class Audit:
    def __init__(self,path:Path|None=None):
        self.path=path or (data_dir()/'computer_control_audit.jsonl')
        self.path.parent.mkdir(parents=True,exist_ok=True)
    def add(self,task_id:str,event:str,**detail):
        clean={k: redact(json.dumps(v,ensure_ascii=False,default=str))[:6000] if k in {'args','result','message'} else v
               for k,v in detail.items() if k not in {'screenshot','secret','api_key','raw_image'}}
        line=json.dumps({'time':time.time(),'task_id':task_id,'event':event,**clean},ensure_ascii=False,default=str)
        with _lock:
            with self.path.open('a',encoding='utf-8') as f:f.write(line+'\n')
    def recent(self,task_id:str,limit:int=100)->list[dict]:
        if not self.path.exists():return []
        # Don't stream unbounded audit files into memory.
        from collections import deque
        with self.path.open(encoding='utf-8') as f:
            entries=deque((json.loads(line) for line in f if line.strip()),maxlen=2000)
        return [e for e in entries if e['task_id']==task_id][-limit:]
