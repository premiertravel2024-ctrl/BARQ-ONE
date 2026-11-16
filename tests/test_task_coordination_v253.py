"""Behavioral coverage for contextual routing and real model/tool handoffs."""
import json
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from agent.task_intent import classify_task
from agent.tool_intent import classify_direct_user_text
from agent import orchestrator as agent
from router.config import Config
from router.engine import Engine


@pytest.mark.parametrize('text',[
    'تقدر تحللي برنامج بالهندسه العكسية ؟',
    'ممكن تفحص تطبيق بالهندسة العكسية؟',
    'Can you reverse engineer this EXE?',
])
def test_reverse_engineering_without_tool_name(text):
    request=classify_direct_user_text(text)
    assert request['integration']=='rea'
    assert request['intent']=='capability'
    assert request['connected'] is False


@pytest.mark.parametrize('text',['What is reverse engineering?', 'اشرح الهندسة العكسية', 'I live in an AREA'])
def test_definitions_do_not_start_integration(text):
    assert classify_direct_user_text(text) is None


def test_one_word_keeps_target_but_does_not_revive_old_topic():
    assert classify_task('كمل',['صلح الملف في المشروع'])['kind']=='coding'
    assert classify_task('حلله',['تقدر تحللي برنامج بالهندسة العكسية؟'])['kind']=='rea'
    assert classify_task('نفذ',['افتح Excel'])['kind']=='computer'
    assert classify_task('كمل',['صلح الملف في المشروع','ما عاصمة فرنسا؟']) is None
    assert classify_task('كمل') is None


def test_screenshot_prompt_never_calls_cloud_or_tools(monkeypatch):
    import api
    cloud=AsyncMock(side_effect=AssertionError('Capability must be handled locally'))
    monkeypatch.setattr(api.engine,'run',cloud)
    monkeypatch.setattr(agent,'invoke',cloud)
    with TestClient(api.app) as client:
        text='تقدر تحللي برنامج بالهندسه العكسية ؟'
        for endpoint in ['/v1/router/chat','/v1/chat/completions']:
            response=client.post(endpoint,json={'messages':[{'role':'user','content':text}]})
            assert response.status_code==200
            assert 'REA' in response.text
            assert 'لا أستطيع' not in response.text
        response=client.post('/v1/agent/task-intent',json={'text':'حلله','previous_user_texts':[text]})
        assert response.json()['intent']['kind']=='rea'
    cloud.assert_not_called()


@pytest.mark.asyncio
async def test_auto_handoff_rejects_invalid_plan_before_accepting_model(tmp_path,monkeypatch):
    import router.engine as mod
    config=Config.model_validate({'providers':[{'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1',
        'models':[{'name':'first','strengths':['coding']},{'name':'second','strengths':['coding']}]}]})
    engine=Engine(config,cache_path=str(tmp_path/'cache.sqlite'))
    refresh=AsyncMock(return_value=config.providers[0]);monkeypatch.setattr(engine,'refresh_local',refresh)
    seen=[]
    async def complete(provider,model,messages):
        seen.append((model.name,messages))
        if model.name=='first':return '{"steps":[{"tool":"imaginary_tool","args":{}}]}'
        return '{"steps":[{"tool":"project_map","args":{}}],"answer":"Inspecting the source"}'
    monkeypatch.setattr(mod,'complete',complete)
    messages=[{'role':'system','content':'Original goal and real tool evidence'}, {'role':'user','content':'Fix the project'}]
    result=await engine.run(messages,use_cache=False,task_hint='coding',response_validator=lambda text:agent.parse_plan(text,set(agent.ACTIONS)))
    assert result['model']=='ollama/second'
    assert result['attempts']
    assert all(item[1]==messages for item in seen)
    # A malformed plan reduces output quality, not provider availability.
    health=engine.health.snapshot()['ollama/first']
    assert health['fail']==0
    assert health['cooldown']==0
    assert health['output_quality']<1.0


@pytest.mark.asyncio
async def test_inspect_runs_reads_then_stops_before_file_changes(tmp_path):
    (tmp_path/'app.py').write_text('print(1)\n')
    class Model:
        async def run(self,messages,**kwargs):
            assert 'ACTIVE USER GOAL' in messages[0]['content']
            if any('Tool outputs' in m['content'] for m in messages):
                step={'tool':'code_replace','args':{'path':'app.py','before':'print(1)','after':'print(2)'}}
            else:step={'tool':'workspace_read','args':{'path':'app.py'}}
            return {'model':'mock/free','content':json.dumps({'steps':[step],'answer':'Next action'})}
    outcome=await agent.prepare_task(Model(),str(tmp_path),[{'role':'user','content':'صلح الملف في المشروع'}])
    assert outcome['preparation_results'][0]['tool']=='workspace_read'
    assert outcome['preparation_results'][0]['success'] is True
    assert outcome['plan']['steps'][0]['tool']=='code_replace'
    assert (tmp_path/'app.py').read_text()=='print(1)\n'
    agent.PENDING.pop(outcome['plan_id'])


@pytest.mark.asyncio
@pytest.mark.parametrize('result',[{'exit_code':1,'stdout':'1 failed'}, {'isError':True,'content':[{'type':'text','text':'analysis failed'}]}])
async def test_failed_tool_result_never_becomes_success(tmp_path,monkeypatch,result):
    from mcp.bridge import SERVERS
    monkeypatch.setattr(SERVERS['rea'],'enabled',True)
    monkeypatch.setattr(agent,'run_tool',AsyncMock(return_value=result))
    monkeypatch.setattr(agent,'invoke',AsyncMock(return_value=result))
    token='failed_tool_test'
    tool='rea_analyze' if 'isError' in result else 'run_tests'
    agent.PENDING[token]={'workspace':str(tmp_path),'model':'auto','messages':[],
        'plan':{'steps':[{'tool':tool,'args':{'name':'analyze'}}]},'round':0,'expires':float('inf')}
    model=type('Model',(),{'run':AsyncMock()})()
    outcome=await agent.execute(model,token,True)
    assert outcome['results'][0]['success'] is False
    model.run.assert_not_called()


@pytest.mark.asyncio
async def test_capability_question_does_not_start_automatic_inspection(tmp_path):
    model=type('Model',(),{'run':AsyncMock()})()
    with pytest.raises(ValueError,match='direct project task'):
        await agent.prepare_task(model,str(tmp_path),[{'role':'user','content':'هل تقدر تستخدم REA؟'}])
    model.run.assert_not_called()
