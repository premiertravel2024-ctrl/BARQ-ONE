"""Behavioral checks for the coordinator; no live models or desktop are assumed."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from brain.coordinator import Brain
from brain.state import TaskStore
from brain.understanding import understand, parse_understanding
from agent import orchestrator as agent
from classifier.tasks import classify
from workspace import manager as files


def coordinator(tmp_path,engine=None):
    return Brain(engine or SimpleNamespace(run=AsyncMock()),TaskStore(tmp_path/'brain.sqlite3'))


def test_current_message_routing_does_not_inherit_an_old_coding_topic():
    task,_=classify([{'role':'user','content':'Fix Python project code'},{'role':'user','content':'خفيف زي السهم'}])
    assert task=='arabic'


@pytest.mark.asyncio
async def test_identity_and_egyptian_feedback_are_local(tmp_path):
    b=coordinator(tmp_path)
    for question in ['انت مين؟','كلمني مصري وبصيغة المفرد']:
        answer=await b.run([{'role':'user','content':question}])
        assert 'برق' in answer['content'] and 'نحن' not in answer['content']
    b.engine.run.assert_not_called()


@pytest.mark.asyncio
async def test_semantic_paraphrase_is_understood_once_then_cached(tmp_path):
    engine=SimpleNamespace(run=AsyncMock(return_value={'model':'mock/reasoning','content':json.dumps({
        'kind':'coding','goal':'Adjust the selected project colors','question':'','task':'coding'})}))
    b=coordinator(tmp_path,engine)
    messages=[{'role':'user','content':'ظبط ألوانه وخليه أهدى'}]
    pending_before=dict(agent.PENDING)
    first=await b.route(messages,'c1',str(tmp_path))
    again=await b.route(messages,'c1',str(tmp_path))
    assert first['intent']['kind']=='coding' and again==first
    assert engine.run.await_count==1
    assert callable(engine.run.call_args.kwargs['response_validator'])
    assert agent.PENDING==pending_before  # Understanding alone cannot grant or run tools.


@pytest.mark.asyncio
async def test_semantic_failure_asks_one_question_instead_of_guessing(tmp_path):
    b=coordinator(tmp_path,SimpleNamespace(run=AsyncMock(side_effect=RuntimeError('offline'))))
    decision=await b.route([{'role':'user','content':'ظبط اللي اتفقنا عليه'}],'c')
    assert decision['intent'] is None
    assert decision['clarification']


@pytest.mark.asyncio
async def test_short_followup_uses_persistent_mission_after_unrelated_chat(tmp_path):
    b=coordinator(tmp_path)
    mission=b.store.begin('c','coding','صلح الخطأ في المشروع',str(tmp_path),b.runtime_id)
    b.store.update(mission['id'],status='blocked')
    decision=await b.route([{'role':'user','content':'ازيك'},{'role':'assistant','content':'تمام'},
                            {'role':'user','content':'ظبطه'}],'c',str(tmp_path))
    assert decision['intent']['goal']=='صلح الخطأ في المشروع'
    assert decision['intent']['contextual']
    b.engine.run.assert_not_called()


@pytest.mark.asyncio
async def test_reply_validator_preserves_singular_identity_and_quoted_documents(tmp_path):
    b=coordinator(tmp_path,SimpleNamespace(run=AsyncMock(return_value={'model':'mock/a','content':'أنا برق، هساعدك.'})))
    await b.run([{'role':'user','content':'ازيك'}])
    validator=b.engine.run.call_args.kwargs['response_validator']
    with pytest.raises(ValueError,match='one assistant'):validator('نحن هنا لمساعدتك')
    b._check_reply('نحن فريق الشركة',[{'role':'user','content':'ترجم نص الرسالة'}])


@pytest.mark.asyncio
async def test_stream_rejects_group_identity_before_visible_text(tmp_path):
    calls=[]
    async def stream(messages,**kwargs):
        calls.append(messages)
        yield {'type':'model','model':'mock/one'}
        yield {'type':'token','content':'نحن هنا لمساعدتك في كل طلباتك.' if len(calls)==1 else 'أنا برق، هساعدك في طلبك خطوة بخطوة.'}
        yield {'type':'done'}
    b=coordinator(tmp_path,SimpleNamespace(stream_run=stream))
    events=[event async for event in b.stream([{'role':'user','content':'ازيك'}])]
    text=''.join(e['content'] for e in events if e['type']=='token')
    assert text=='أنا برق، هساعدك في طلبك خطوة بخطوة.'
    assert len(calls)==2
    assert events[-1]['type']=='done'


@pytest.mark.asyncio
async def test_stream_remains_incremental_after_prefix_gate(tmp_path):
    proceed=asyncio.Event();first=asyncio.Event()
    async def stream(messages,**kwargs):
        yield {'type':'model','model':'mock/one'}
        yield {'type':'token','content':'أنا برق، هراجع الملف وأوضحلك اللي محتاج يتغير.'}
        first.set();await proceed.wait()
        yield {'type':'token','content':' وبعدها نكمل.'}
        yield {'type':'done'}
    b=coordinator(tmp_path,SimpleNamespace(stream_run=stream))
    output=[]
    async def collect():
        async for event in b.stream([{'role':'user','content':'اشرح'}]):output.append(event)
    job=asyncio.create_task(collect())
    await asyncio.wait_for(first.wait(),1)
    assert any(e['type']=='token' for e in output)
    assert not any(e['type']=='done' for e in output)
    proceed.set();await job


@pytest.mark.asyncio
async def test_full_inspect_edit_save_validate_lifecycle(tmp_path,monkeypatch):
    source=tmp_path/'app.py';source.write_text('print(1)\n')
    class Model:
        def __init__(self):self.calls=0;self.messages=[]
        async def run(self,messages,**kwargs):
            self.calls+=1;self.messages.append(messages)
            step={1:{'tool':'workspace_read','args':{'path':'app.py'}},
                  2:{'tool':'code_replace','args':{'path':'app.py','before':'print(1)','after':'print(2)'}},
                  3:{'tool':'run_tests','args':{}}}.get(self.calls)
            return {'model':f'mock/model-{self.calls}','content':json.dumps({'steps':[step] if step else [],'answer':'الخطوة جاهزة.'})}
    b=coordinator(tmp_path,Model())
    result=await b.prepare(str(tmp_path),[{'role':'user','content':'صلح الملف في المشروع'}],conversation_id='c')
    mission=b.store.get(result['task_id'])
    assert mission['status']=='awaiting_approval'
    assert source.read_text()=='print(1)\n'
    with pytest.raises(ValueError,match='another conversation'):
        await b.execute(result['plan_id'],True,'other')
    preview=await b.execute(result['plan_id'],True,'c')
    assert preview['task_status']=='awaiting_save'
    approval=preview['pending_edit']['approval_id']
    b.check_save(approval,'c');saved=files.apply(approval,True);b.saved(approval,saved)
    assert source.read_text()=='print(2)\n'
    next_step=await b.resume(approval,saved['backup_id'],True,'c')
    assert next_step['task_status']=='awaiting_approval'
    monkeypatch.setattr(agent,'run_tool',AsyncMock(return_value={'exit_code':0,'stdout':'passed'}))
    done=await b.execute(next_step['next_plan']['plan_id'],True,'c')
    task=b.store.get(result['task_id'])
    assert done['task_status']=='completed'
    assert task['saved_paths']==['app.py']
    assert any(e['tool']=='saved_edit' for e in task['evidence'])
    assert any(e['tool']=='run_tests' and e['success'] for e in task['evidence'])
    assert all('صلح الملف في المشروع' in messages[0]['content'] for messages in b.engine.messages)


def test_restart_retains_goal_but_does_not_replay_old_approvals(tmp_path):
    b=coordinator(tmp_path)
    task=b.store.begin('c','coding','Fix project',str(tmp_path),b.runtime_id)
    b.store.update(task['id'],status='awaiting_approval',plan_id='old-token')
    restored=Brain(b.engine,TaskStore(tmp_path/'brain.sqlite3'))
    state=restored.state('c')
    assert state['goal']=='Fix project' and state['status']=='interrupted'
    assert state['plan_id'] is None


def test_cancellation_invalidates_plan_and_edit_tokens(tmp_path):
    b=coordinator(tmp_path)
    task=b.store.begin('c','coding','Fix project',str(tmp_path),b.runtime_id)
    b.store.update(task['id'],status='awaiting_save',approval_id='edit')
    agent.PENDING_EDITS['edit']={'expires':float('inf')}
    agent.EDIT_PROPOSALS['edit']={'content':'do not apply'}
    assert b.cancel('c')['cancelled']
    assert 'edit' not in agent.PENDING_EDITS and 'edit' not in agent.EDIT_PROPOSALS
    assert b.store.latest('c')['status']=='cancelled'


def test_evidence_is_redacted_and_passive_state_has_no_source_contents(tmp_path):
    b=coordinator(tmp_path)
    task=b.store.begin('c','coding','Fix project',str(tmp_path),b.runtime_id)
    b.store.evidence(task['id'],[{'tool':'workspace_read','success':True,'result':'password="secret-password"'}])
    saved=b.store.get(task['id'])
    assert 'secret-password' not in json.dumps(saved)
    assert 'evidence' not in b.store.public(saved)


@pytest.mark.asyncio
async def test_planner_cannot_claim_an_edit_from_read_evidence_only(tmp_path):
    b=coordinator(tmp_path)
    task=b.store.begin('c','coding','صلح الملف في المشروع',str(tmp_path),b.runtime_id)
    outcome=b._attach(task['id'],{'model':'mock/free','results':[{'tool':'workspace_read','success':True,'result':'print(1)'}],
                                'answer':'تم تعديل الملف'})
    assert outcome['task_status']=='blocked'
    assert outcome['blocked'] is True
    assert 'لسه' in outcome['answer']


@pytest.mark.asyncio
async def test_replanning_continues_same_mission_and_invalidates_old_step(tmp_path,monkeypatch):
    b=coordinator(tmp_path)
    task=b.store.begin('c','coding','افحص الملف في المشروع',str(tmp_path),b.runtime_id)
    b.store.evidence(task['id'],[{'tool':'workspace_read','success':True,'result':'Read evidence'}])
    b.store.update(task['id'],status='awaiting_approval',plan_id='previous')
    agent.PENDING['previous']={'expires':float('inf')}
    async def prepare(engine,workspace,messages,model,**kwargs):
        assert kwargs['task_intent']['goal']=='افحص الملف في المشروع'
        assert 'Read evidence' in json.dumps(messages,ensure_ascii=False)
        return {'plan_id':'new','plan':{'steps':[{'tool':'run_tests','args':{}}],'answer':'جاهز'},'preparation_results':[]}
    monkeypatch.setattr(agent,'prepare_task',prepare)
    result=await b.prepare(str(tmp_path),[{'role':'user','content':'كمل'}],conversation_id='c')
    assert result['task_id']==task['id']
    assert 'previous' not in agent.PENDING
    assert b.store.get(task['id'])['evidence'][0]['result']=='Read evidence'


@pytest.mark.asyncio
async def test_cancel_during_tool_records_real_result_and_stops_replanning(tmp_path,monkeypatch):
    started=asyncio.Event();finish=asyncio.Event()
    async def run_tool(*args,**kwargs):
        started.set();await finish.wait();return {'exit_code':0,'stdout':'Actual successful result'}
    monkeypatch.setattr(agent,'run_tool',run_tool)
    b=coordinator(tmp_path)
    task=b.store.begin('c','coding','اختبر المشروع',str(tmp_path),b.runtime_id)
    agent.PENDING['running']={'workspace':str(tmp_path),'model':'auto','messages':[],
        'plan':{'steps':[{'tool':'run_tests','args':{}}]},'round':0,'expires':float('inf')}
    b.store.update(task['id'],status='awaiting_approval',plan_id='running')
    operation=asyncio.create_task(b.execute('running',True,'c'))
    await started.wait();b.cancel('c');finish.set()
    result=await operation
    assert result['task_status']=='cancelled'
    assert result['results'][0]['success'] is True
    assert b.store.get(task['id'])['evidence'][0]['success'] is True
    b.engine.run.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_local_only_never_calls_cloud_when_ollama_missing(tmp_path):
    engine=SimpleNamespace(run=AsyncMock(),refresh_local=AsyncMock(),config=SimpleNamespace(providers=[]))
    b=coordinator(tmp_path,engine)
    with pytest.raises(ValueError,match='Ollama'):
        await b.run([{'role':'user','content':'اشرح حاجة'}],model='local-only')
    engine.run.assert_not_called()


def test_semantic_contract_does_not_accept_tool_calls_as_intents():
    with pytest.raises(ValueError):
        parse_understanding('{"kind":"run_command","task":"coding","goal":"x","question":""}')


def test_brain_api_returns_singular_reply_without_provider_call(tmp_path,monkeypatch):
    import api
    from fastapi.testclient import TestClient
    b=coordinator(tmp_path)
    monkeypatch.setattr(api,'brain',b)
    with TestClient(api.app) as client:
        response=client.post('/v1/brain/route',json={'conversation_id':'c','messages':[{'role':'user','content':'كلمني مصري وبصيغة المفرد'}]})
        assert response.status_code==200
        assert response.json()['reply']=='أنا برق، وهكلمك بالمصري وبصيغة المفرد.'
        assert client.get('/v1/brain/state?conversation_id=c').json()=={'task':None}
    b.engine.run.assert_not_called()


@pytest.mark.asyncio
async def test_contextual_reverse_engineering_discovers_rea_without_repeating_its_name(tmp_path,monkeypatch):
    from mcp.bridge import SERVERS
    monkeypatch.setattr(SERVERS['rea'],'enabled',True)
    monkeypatch.setattr(agent,'mcp_runner_available',lambda server:True)
    monkeypatch.setattr(agent,'discover',AsyncMock(return_value=[{'name':'inspect_binary','inputSchema':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}}]))
    invoke=AsyncMock();monkeypatch.setattr(agent,'invoke',invoke)
    class Model:
        async def run(self,messages,**kwargs):
            assert 'inspect_binary' in messages[0]['content']
            return {'model':'mock/rea','content':json.dumps({'steps':[{'tool':'rea_analyze','args':{'name':'inspect_binary','arguments':{'path':str(tmp_path/'app.exe')}}}],'answer':'التحليل جاهز لموافقتك.'})}
    b=coordinator(tmp_path,Model())
    output=await b.prepare(str(tmp_path),[{'role':'user','content':'تقدر تحللي برنامج بالهندسه العكسية؟'},
        {'role':'assistant','content':'اختار البرنامج.'},{'role':'user','content':'حلله'}],conversation_id='c')
    assert output['plan']['steps'][0]['tool']=='rea_analyze'
    assert output['task_status']=='awaiting_approval'
    invoke.assert_not_called()
    agent.PENDING.pop(output['plan_id'],None)
