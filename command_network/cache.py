"""Privacy aware bounded exact cache and in-flight coalescing for read-only tasks."""
import asyncio,hashlib,json,time
from collections import OrderedDict
class ExactCache:
    def __init__(self,limit=250,ttl=600):
        self.entries=OrderedDict();self.limit=limit;self.ttl=ttl;self.pending={};self.lock=asyncio.Lock()
    @staticmethod
    def key(request,task_type):
        safe={'messages':request.messages,'mode':request.mode,'model':request.model,'task_type':task_type,'privacy':request.privacy}
        return hashlib.sha256(json.dumps(safe,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    def get(self,key):
        item=self.entries.get(key)
        if not item:return None
        expires,value=item
        if time.monotonic()>expires:self.entries.pop(key,None);return None
        self.entries.move_to_end(key);return value
    def put(self,key,value):
        self.entries[key]=(time.monotonic()+self.ttl,value)
        self.entries.move_to_end(key)
        while len(self.entries)>self.limit:self.entries.popitem(last=False)
    async def coalesce(self,key,operation):
        async with self.lock:
            if key in self.pending:task=self.pending[key]
            else:
                task=asyncio.create_task(operation());self.pending[key]=task
        try:return await asyncio.shield(task)
        finally:
            async with self.lock:
                if task.done() and self.pending.get(key) is task:self.pending.pop(key,None)
