"""Ephemeral, display-only model drafts. They never become tool/save approvals."""
from contextvars import ContextVar
from contextlib import contextmanager
from pathlib import Path
import json,time,uuid

ACTIVE=ContextVar('barq_live_code',default=None)
MAX_TEXT=180000


def partial_json(text):
    """Decode only complete escapes from an unfinished JSON prefix, without eval."""
    pos=text.find('{')
    if pos<0:return {}
    size=len(text)
    def skip():
        nonlocal pos
        while pos<size and text[pos].isspace():pos+=1
    def string():
        nonlocal pos
        pos+=1;start=pos;end=pos
        while pos<size:
            char=text[pos]
            if char=='"':
                raw=text[start:pos];pos+=1
                return json.loads('"'+raw+'"'),True
            if char=='\\':
                if pos+1>=size:break
                width=6 if text[pos+1]=='u' else 2
                if pos+width>size:break
                pos+=width;end=pos
            else:pos+=1;end=pos
        raw=text[start:end]
        value=json.loads('"'+raw+'"')
        if value and 0xD800<=ord(value[-1])<=0xDBFF:value=value[:-1]
        return value,False
    def value(depth=0):
        nonlocal pos
        if depth>16:raise ValueError('Deep draft')
        skip()
        if pos>=size:return None,False
        if text[pos]=='"':return string()
        if text[pos]=='{':
            pos+=1;out={}
            while pos<size:
                skip()
                if pos>=size:return out,False
                if text[pos]=='}':pos+=1;return out,True
                if text[pos]!='"':return out,False
                key,complete=string();skip()
                if not complete or pos>=size or text[pos]!=':':return out,False
                pos+=1;item,complete=value(depth+1);out[key]=item;skip()
                if not complete:return out,False
                if pos<size and text[pos]==',':pos+=1;continue
                if pos<size and text[pos]=='}':pos+=1;return out,True
                return out,False
            return out,False
        if text[pos]=='[':
            pos+=1;out=[]
            while pos<size:
                skip()
                if pos<size and text[pos]==']':pos+=1;return out,True
                item,complete=value(depth+1);out.append(item);skip()
                if not complete:return out,False
                if pos<size and text[pos]==',':pos+=1;continue
                if pos<size and text[pos]==']':pos+=1;return out,True
                return out,False
            return out,False
        item,end=json.JSONDecoder().raw_decode(text[pos:]);pos+=end;return item,True
    try:return value()[0]
    except (ValueError,TypeError,RecursionError):return {}


class Draft:
    def __init__(self,workspace):
        self.workspace=str(Path(workspace).resolve()) if workspace else ''
        self.id=uuid.uuid4().hex;self.text='';self.status='waiting';self.model='';self.updated=time.monotonic();self.attempt=0
    def begin(self,model):
        from core.generation import SOURCE_TARGET
        self.source_target=SOURCE_TARGET.get()
        self.attempt+=1;self.text='';self.model=model;self.status='streaming';self.updated=time.monotonic()
    def append(self,piece):
        if len(self.text)+len(piece)>MAX_TEXT:raise ValueError('Live plan too large')
        self.text+=piece;self.updated=time.monotonic()
    def finish(self,success):
        self.status='ready' if success else 'interrupted';self.updated=time.monotonic()
        if not success:self.text=''
    def public(self):
        if getattr(self,'source_target',None):
            from coding.source_contract import source_prefix
            return {'id':self.id,'attempt':self.attempt,'workspace':self.workspace,'status':self.status,'model':self.model,
                    'path':self.source_target,'code':source_prefix(self.text,self.source_target),'partial_edit':False,'validated':self.status=='ready'}
        parsed=partial_json(self.text);steps=parsed.get('steps',[]) if isinstance(parsed,dict) else []
        step=steps[0] if isinstance(steps,list) and steps and isinstance(steps[0],dict) else {}
        args=step.get('args',{});args=args if isinstance(args,dict) else {}
        tool=step.get('tool');code=args.get('after' if tool=='code_replace' else 'content','') if tool in {'code_replace','workspace_edit'} else ''
        path=args.get('path','')
        # Normalize escaped surrogate pairs before JSON serialization.
        code=code.encode('utf-16-le','surrogatepass').decode('utf-16-le','replace') if isinstance(code,str) else ''
        return {'id':self.id,'attempt':self.attempt,'workspace':self.workspace,'status':self.status,'model':self.model,
                'path':path[:1000] if isinstance(path,str) else '', 'code':code,'partial_edit':tool=='code_replace','validated':self.status=='ready'}


class LiveCode:
    def __init__(self):self.items={}
    @contextmanager
    def observe(self,conversation,workspace):
        if not conversation:
            yield;return
        now=time.monotonic()
        self.items={key:item for key,item in self.items.items() if now-item.updated<900}
        if len(self.items)>=32:self.items.pop(next(iter(self.items)))
        item=Draft(workspace);self.items[conversation]=item;token=ACTIVE.set(item)
        try:yield
        finally:
            ACTIVE.reset(token)
            if item.status=='streaming':item.finish(False)
    def view(self,conversation,workspace):
        item=self.items.get(conversation)
        if not item or time.monotonic()-item.updated>900 or item.workspace!=str(Path(workspace).resolve()):return None
        return item.public()

live_code=LiveCode()
