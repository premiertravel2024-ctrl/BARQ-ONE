"""Optional private semantic cache: local Ollama embeddings, SQLite, no cloud calls.

Defaults off unless BARQ_SEMANTIC_CACHE=1. Ollama model tags are checked locally
and nothing is ever pulled/downloaded. No tools, attachments or conversation data.
"""
from __future__ import annotations
from core.sqlite import connect as barq_sqlite_connect
import json,math,os,sqlite3,time
from pathlib import Path
import httpx
from core.paths import state_file
from .triage import Triage

class SemanticCache:
    def __init__(self,path=None,embedder=None,clock=None,limit=200,ttl=3600,threshold=.93):
        self.path=Path(path) if path else state_file('semantic_cache.sqlite3')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.embedder=embedder or self._embed
        self.clock=clock or time.time
        self.limit=limit;self.ttl=ttl;self.threshold=threshold
        self.last_status='offline/local embedding not checked'
        with barq_sqlite_connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, scope TEXT, vector TEXT, content TEXT, expires REAL)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_semantic_expires ON items(expires)')
    async def _embed(self,text):
        if os.environ.get('BARQ_SEMANTIC_CACHE')!='1':
            self.last_status='semantic cache disabled in settings'
            return None
        # Loopback only. No provider API keys or telemetry.
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.5,connect=.4),trust_env=False) as client:
                tags=await client.get('http://127.0.0.1:11434/api/tags')
                tags.raise_for_status()
                names={m.get('name','') for m in tags.json().get('models',[]) if isinstance(m,dict)}
                model=os.environ.get('BARQ_LOCAL_EMBED_MODEL','bge-m3')
                if not any(v==model or v.startswith(model+':') for v in names):
                    self.last_status='لم يتم العثور على BGE-M3 محليًا؛ تم تعطيل التخزين الدلالي'
                    return None
                resp=await client.post('http://127.0.0.1:11434/api/embed',json={'model':model,'input':text})
                resp.raise_for_status()
                vec=resp.json().get('embeddings',[None])[0]
                self.last_status='التمثيلات المحلية جاهزة'
                return vec
        except (OSError,ValueError,KeyError,httpx.HTTPError):
            self.last_status='Ollama غير متاح للتمثيلات الدلالية'
            return None
    @staticmethod
    def _unit(vector):
        if not isinstance(vector,list) or not vector or len(vector)>10000:return None
        if not all(isinstance(x,(float,int)) and math.isfinite(x) for x in vector):return None
        norm=math.sqrt(sum(x*x for x in vector))
        return [round(x/norm,8) for x in vector] if norm else None
    @staticmethod
    def eligible(req,profile):
        return Triage.cacheable(req) and profile.task_type not in ('tool','vision','long_document') and not profile.needs_tools
    @staticmethod
    def scope(req,profile):return '|'.join((profile.task_type,profile.language,req.mode,req.model))
    async def get(self,req,profile):
        if not self.eligible(req,profile):return None
        text=str(req.messages[-1].get('content',''))
        vec=self._unit(await self.embedder(text))
        if not vec:return None
        now=self.clock()
        with barq_sqlite_connect(self.path) as db:
            db.execute('DELETE FROM items WHERE expires<?',(now,))
            rows=db.execute('SELECT vector,content FROM items WHERE scope=?',(self.scope(req,profile),)).fetchall()
        closest=None;best=0
        for raw,value in rows:
            try:old=json.loads(raw)
            except ValueError:continue
            if len(old)!=len(vec):continue
            sim=sum(a*b for a,b in zip(old,vec))
            if sim>=self.threshold and sim>best:best=sim;closest=value
        if closest:
            try:return json.loads(closest)
            except ValueError:return None
        return None
    async def put(self,req,profile,value):
        if not self.eligible(req,profile):return False
        vec=self._unit(await self.embedder(str(req.messages[-1].get('content',''))))
        if not vec:return False
        value={k:value[k] for k in ('content','model','task','offline') if k in value}
        if not value.get('content'):return False
        with barq_sqlite_connect(self.path) as db:
            db.execute('DELETE FROM items WHERE expires<?',(self.clock(),))
            db.execute('INSERT INTO items(scope,vector,content,expires) VALUES(?,?,?,?)',(
                self.scope(req,profile),json.dumps(vec),json.dumps(value,ensure_ascii=False),self.clock()+self.ttl))
            excess=db.execute('SELECT COUNT(*) FROM items').fetchone()[0]-self.limit
            if excess>0:db.execute('DELETE FROM items WHERE id IN (SELECT id FROM items ORDER BY id LIMIT ?)',(excess,))
        return True
