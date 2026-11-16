"""Persistent, privacy-safe quota accounting. Only model identifiers and usage counts.

A single quota key is derived from the provider's advertised scope: model,
provider or account. SQLite events survive reboot. Callers may pass a fake clock.
"""
from __future__ import annotations
from core.sqlite import connect as barq_sqlite_connect
import asyncio,sqlite3,threading,time
from collections import defaultdict,deque
from pathlib import Path


def estimate_tokens(value):
    """Deliberately conservative; not a provider tokenizer."""
    return max(1,(len(str(value))+2)//3)

def quota_key(provider,model):
    return provider.name if provider.quota_scope in ('provider','account') else provider.name+'/'+model.name

class QuotaManager:
    def __init__(self,clock=None,margin=0,db_path=None):
        self.clock=clock or time.time;self.margin=margin;self.calls=defaultdict(deque);self.tokens=defaultdict(deque)
        self.path=Path(db_path) if db_path else None
        self._lock=threading.RLock();self._semaphores={};self.cooldowns={};self.remote_caps={}
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with barq_sqlite_connect(self.path) as db:
                db.execute('CREATE TABLE IF NOT EXISTS usage(scope TEXT NOT NULL, ts REAL NOT NULL, requests INTEGER NOT NULL, tokens INTEGER NOT NULL)')
                db.execute('CREATE INDEX IF NOT EXISTS idx_usage_scope_time ON usage(scope,ts)')
                since=self.clock()-86400
                db.execute('DELETE FROM usage WHERE ts<?',(since,))
                for key,ts,calls,tokens in db.execute('SELECT scope,ts,requests,tokens FROM usage'):
                    if calls:self.calls[key].append((ts,calls))
                    if tokens:self.tokens[key].append((ts,tokens))
    def _prune(self,key):
        now=self.clock()
        for queue in (self.calls[key],self.tokens[key]):
            while queue and queue[0][0]<=now-86400:queue.popleft()
    def _cap(self,number):return max(1,int(number*(1-self.margin))) if number else 0
    def allowed(self,key,rpm=0,rpd=0,tpm=0,expected_tokens=0,tpd=0):
        with self._lock:
            self._prune(key);now=self.clock()
            c=self.calls[key];t=self.tokens[key]
            if now<self.cooldowns.get(key,0):return False
            remote=self.remote_caps.get(key,{})
            if 'remaining_requests' in remote and remote['remaining_requests']<=0:return False
            return not ((rpm and sum(n for ts,n in c if ts>now-60)>=self._cap(rpm)) or
                (rpd and sum(n for _,n in c)>=self._cap(rpd)) or
                (tpm and sum(n for ts,n in t if ts>now-60)+expected_tokens>self._cap(tpm)) or
                (tpd and sum(n for _,n in t)+expected_tokens>self._cap(tpd)))
    def record(self,key,estimated_tokens=0,requests=1):
        now=self.clock()
        with self._lock:
            self._prune(key)
            if requests:self.calls[key].append((now,requests))
            if estimated_tokens:self.tokens[key].append((now,max(0,estimated_tokens)))
            if self.path:
                with barq_sqlite_connect(self.path) as db:
                    db.execute('INSERT INTO usage VALUES(?,?,?,?)',(key,now,requests,max(0,estimated_tokens)))
    def reconcile(self,key,estimated,actual):
        """Replace an advance token estimate with actual API usage, when available."""
        delta=int(actual)-int(estimated)
        if not delta:return
        now=self.clock()
        with self._lock:
            self._prune(key)
            self.tokens[key].append((now,delta))
            if self.path:
                with barq_sqlite_connect(self.path) as db:
                    db.execute('INSERT INTO usage VALUES(?,?,?,?)',(key,now,0,delta))
    def add_output(self,key,tokens):
        if tokens>0:self.record(key,tokens,requests=0)
    def remaining(self,key,rpd):
        with self._lock:
            self._prune(key)
            return max(0,self._cap(rpd)-sum(n for _,n in self.calls[key])) if rpd else None
    def semaphore(self,key,max_concurrent):
        if max_concurrent<=0:return None
        with self._lock:
            k=(key,max_concurrent)
            if k not in self._semaphores:self._semaphores[k]=asyncio.Semaphore(max_concurrent)
            return self._semaphores[k]
    def observe_headers(self,key,headers):
        """Only react to provider-supplied actual limits; never query quota in background."""
        with self._lock:
            for label in ('x-ratelimit-remaining-requests','ratelimit-remaining'):
                raw=headers.get(label)
                if raw is not None:
                    try:self.remote_caps[key]={'remaining_requests':max(0,int(raw))}
                    except (ValueError,TypeError):pass
            value=headers.get('retry-after')
            if value:
                try:self.cooldowns[key]=self.clock()+max(0,min(86400,float(value)))
                except (ValueError,TypeError):pass
