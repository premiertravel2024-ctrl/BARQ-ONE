"""Regression: typing 'REA' in ordinary chat must not turn into LLM tool denial."""
import json
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from agent import tool_intent
from agent import orchestrator as agent
from mcp import bridge


def test_rea_named_by_user_is_read_only(monkeypatch):
    monkeypatch.setattr(tool_intent, 'available', lambda s: True)
    monkeypatch.setattr(bridge.SERVERS['rea'], 'enabled', False)
    ask=tool_intent.classify_direct_user_text('لو بعتلك برنامج تقدر تحلله باستخدام أداة rea؟')
    assert ask['integration']=='rea'
    assert ask['intent']=='capability'
    assert ask['enabled'] is False
    assert ask['connected'] is False
    assert ask['requires_approval'] is True
    directive=tool_intent.classify_direct_user_text('شغل أداة REA وحلل المشروع')
    assert directive['intent']=='request'
    assert tool_intent.classify_direct_user_text('What is reverse engineering?') is None
    assert tool_intent.classify_direct_user_text('I live in an AREA') is None


def test_intent_endpoint_does_not_execute_tools(monkeypatch):
    from api import app
    monkeypatch.setattr(tool_intent,'available',lambda server: True)
    called=[]
    monkeypatch.setattr(bridge,'invoke',lambda *args:called.append(args))
    with TestClient(app) as client:
        response=client.post('/v1/integrations/intent',json={'text':'شغل REA على مشروعي'})
        assert response.status_code==200
        req=response.json()['tool_request']
        assert req['integration']=='rea' and req['connected'] is False
        assert client.post('/v1/integrations/intent',json={'text':'ازيك'}).json()['tool_request'] is None
    assert not called


def test_schema_and_tool_name_must_be_really_discovered():
    valid='{"steps":[{"tool":"rea_analyze","args":{"name":"real_tool","arguments":{"path":"test.exe"}}}]}'
    assert agent.parse_plan(valid,set(agent.ACTIONS),{'real_tool'})['steps'][0]['tool']=='rea_analyze'
    with pytest.raises(ValueError,match='not advertised'):
        agent.parse_plan(valid,set(agent.ACTIONS),{'another_tool'})
    with pytest.raises(ValueError,match='not advertised'):
        agent.parse_plan(valid,set(agent.ACTIONS))
    with pytest.raises(ValueError,match='arguments must'):
        agent.parse_plan('{"steps":[{"tool":"rea_analyze","args":{"name":"real_tool","arguments":[]}}]}',set(agent.ACTIONS))


@pytest.mark.asyncio
async def test_explicit_rea_plan_uses_live_schema_and_waits_for_approval(tmp_path,monkeypatch):
    (tmp_path/'app.js').write_text('console.log(1)',encoding='utf-8')
    monkeypatch.setattr(bridge.SERVERS['rea'],'enabled',True)
    monkeypatch.setattr(agent,'mcp_runner_available',lambda s:True)
    fake_list=[{'name':'analyze_javascript', 'description':'Analyze a local JavaScript app',
                'inputSchema':{'type':'object','required':['target'],
                               'properties':{'target':{'type':'string','description':'absolute path'}}}}]
    discover=AsyncMock(return_value=fake_list)
    invoke=AsyncMock(return_value={'content':[{'type':'text','text':'Found Electron imports'}]})
    monkeypatch.setattr(agent,'discover',discover)
    monkeypatch.setattr(agent,'invoke',invoke)
    class Model:
        calls=0
        async def run(self,messages,**kwargs):
            self.calls+=1
            if self.calls==1:
                assert 'analyze_javascript' in messages[0]['content']
                return {'model':'mock/free','content':json.dumps({'reason':'Inspect app',
                    'steps':[{'tool':'rea_analyze','args':{'name':'analyze_javascript','arguments':{'target':str(tmp_path)}}}],
                    'answer':'Review before execution'})}
            return {'model':'mock/free','content':'{"steps":[],"answer":"REA examined the project."}'}
    m=Model()
    token=await agent.plan(m,str(tmp_path),[{'role':'user','content':'استخدم REA لتحليل المشروع'}])
    assert discover.await_count==1
    assert invoke.await_count==0
    with pytest.raises(ValueError,match='Approval'):
        await agent.execute(m,token['plan_id'],False)
    assert invoke.await_count==0
    outcome=await agent.execute(m,token['plan_id'],True)
    assert outcome['results'][0]['success'] is True
    assert invoke.await_count==1
    assert outcome['answer']=='REA examined the project.'


@pytest.mark.asyncio
async def test_rea_server_unavailable_fails_before_model_or_tools(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge.SERVERS['rea'],'enabled',False)
    run=AsyncMock()
    with pytest.raises(ValueError,match='not enabled'):
        await agent.plan(type('Dummy',(),{'run':run})(),str(tmp_path),[{'role':'user','content':'استخدم REA'}])
    assert run.await_count==0


def test_frontend_chat_and_agent_have_explicit_handoff():
    from pathlib import Path
    root=Path(__file__).resolve().parent.parent/'frontend/src'
    client=(root/'lib/chat.ts').read_text(encoding='utf-8')
    component=(root/'components/chat/Message.tsx').read_text(encoding='utf-8')
    studio=(root/'components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    assert '/v1/integrations/intent' in client
    assert 'toolRequest' in component and 'setToolHandoff' in component
    assert 'موافقة' in studio and 'planAgent' in studio
