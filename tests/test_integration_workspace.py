import json,sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from workspace import manager as work
from core.history import ConversationStore
from core.models import set_provider
from mcp import bridge
from agent import orchestrator
from build import jobs


def test_workspace_safe_lifecycle(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'userdata'))
    repo=tmp_path/'repo';repo.mkdir();(repo/'a.py').write_text('print(1)\n',encoding='utf8')
    assert work.listing(str(repo))[0]['path']=='a.py'
    assert work.read_text(str(repo),'a.py')=='print(1)\n'
    with pytest.raises(ValueError):work.read_text(str(repo),'../outside.py')
    with pytest.raises(ValueError):work.read_text(str(repo),'.env')
    with pytest.raises(ValueError):work.propose(str(repo),'../bad.py','oops')
    edit=work.propose(str(repo),'a.py','print(2)\n')
    assert '-print(1)' in edit['diff'] and '+print(2)' in edit['diff']
    with pytest.raises(ValueError):work.apply(edit['approval_id'],False)
    result=work.apply(edit['approval_id'],True)
    assert work.read_text(str(repo),'a.py')=='print(2)\n'
    assert work.undo(result['backup_id'],True)['restored']=='a.py'
    assert work.read_text(str(repo),'a.py')=='print(1)\n'
    with pytest.raises(ValueError):work.undo(result['backup_id'],True)


def test_workspace_conflict_and_symlinks(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'ud'))
    repo=tmp_path/'repo';repo.mkdir();out=tmp_path/'secret.py';out.write_text('sensitive')
    try:(repo/'shortcut.py').symlink_to(out)
    except (OSError,NotImplementedError):pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError):work.read_text(str(repo),'shortcut.py')
    (repo/'x.py').write_text('old')
    edit=work.propose(str(repo),'x.py','new')
    (repo/'x.py').write_text('someone else updated')
    with pytest.raises(ValueError,match='changed'):work.apply(edit['approval_id'],True)
    assert (repo/'x.py').read_text()=='someone else updated'


def test_conversation_sqlite_persistence(tmp_path):
    db=tmp_path/'history.db'
    h=ConversationStore(db);h.put('chat-1','Egyptian Arabic',[{'role':'user','content':'إزيك'}])
    assert ConversationStore(db).get('chat-1')['messages'][0]['content']=='إزيك'
    assert len(h.list())==1
    h.delete('chat-1')
    with pytest.raises(ValueError):h.get('chat-1')


def test_provider_setting_persist(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'appdata'))
    result=set_provider('groq',enabled=False,priority=35)
    assert result['updated']
    from router.config import load_config
    p=next(p for p in load_config().providers if p.name=='groq')
    assert not p.enabled and p.priority==35
    with pytest.raises(ValueError):set_provider('wrong-one',enabled=True)
    with pytest.raises(ValueError):set_provider('groq',priority=101)

@pytest.mark.asyncio
async def test_mock_mcp_wire_protocol(tmp_path):
    fake=tmp_path/'fake_server.py'
    fake.write_text('''import json,sys
for line in sys.stdin:
  m=json.loads(line)
  if 'id' not in m:continue
  if m['method']=='initialize':result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'fake','version':'1'}}
  elif m['method']=='tools/list':result={'tools':[{'name':'inspect','description':'Read only','inputSchema':{'type':'object'}}]}
  elif m['method']=='tools/call':result={'content':[{'type':'text','text':m['params']['arguments'].get('q','')}]} 
  else:result={}
  print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
''')
    s=bridge.MCPServer('mock',sys.executable,[str(fake)],True,10)
    bridge.SERVERS['mock']=s
    try:
        tools=await bridge.discover('mock')
        assert tools[0]['name']=='inspect'
        response=await bridge.invoke('mock','inspect',{'q':'Hello REA'})
        assert response['content'][0]['text']=='Hello REA'
        with pytest.raises(bridge.MCPError):await bridge.invoke('mock','nonexistent',{})
    finally:bridge.SERVERS.pop('mock',None)

@pytest.mark.asyncio
async def test_agent_approval_feedback_loop(tmp_path):
    (tmp_path/'x.py').write_text('print(123)',encoding='utf8')
    class FakeEngine:
        def __init__(self):self.calls=0
        async def run(self,*args,**kwargs):
            self.calls+=1
            content=(json.dumps({'reason':'Inspect code','steps':[{'tool':'workspace_read','args':{'path':'x.py'}}],'answer':'Need file'})
                     if self.calls==1 else json.dumps({'reason':'Review result','steps':[],'answer':'x.py prints 123'}))
            return {'model':'mock/free','content':content}
    engine=FakeEngine()
    item=await orchestrator.plan(engine,str(tmp_path),[{'role':'user','content':'Inspect x.py'}])
    assert item['plan']['steps'][0]['tool']=='workspace_read'
    with pytest.raises(ValueError,match='Approval'):await orchestrator.execute(engine,item['plan_id'],False)
    done=await orchestrator.execute(engine,item['plan_id'],True)
    assert done['answer']=='x.py prints 123'
    assert 'print(123)' in done['results'][0]['result']
    with pytest.raises(ValueError,match='expired'):await orchestrator.execute(engine,item['plan_id'],True)


def test_agent_plan_rejects_unlisted_tools():
    with pytest.raises(ValueError):orchestrator.parse_plan('{"steps":[{"tool":"delete_disk","args":{}}]}',set(orchestrator.ACTIONS))
    with pytest.raises(ValueError):orchestrator.parse_plan('{"steps":[{"tool":"workspace_list","args":{}},{"tool":"workspace_read","args":{"path":"a.py"}}]}',set(orchestrator.ACTIONS))


def test_windows_builder_gate(tmp_path):
    if sys.platform!='win32':
        with pytest.raises(jobs.BuildError,match='Windows'):jobs.preview(str(tmp_path),'python','main.py','Sample')


def test_api_approval_guard(tmp_path):
    from api import app
    (tmp_path/'hello.py').write_text('hi',encoding='utf8')
    client=TestClient(app)
    r=client.post('/v1/workspace/edit/preview',json={'workspace':str(tmp_path),'path':'hello.py','content':'bye'})
    assert r.status_code==200
    approval=r.json()['approval_id']
    blocked=client.post('/v1/workspace/edit/apply',json={'approval_id':approval,'confirmed':False})
    assert blocked.status_code==400
    ok=client.post('/v1/workspace/edit/apply',json={'approval_id':approval,'confirmed':True})
    assert ok.status_code==200 and (tmp_path/'hello.py').read_text()=='bye'
    status=client.get('/v1/mcp/servers')
    assert status.status_code==200 and any(x['id']=='rea' for x in status.json()['servers'])
