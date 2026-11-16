"""Real routing/adapters with controlled HTTP, including outages and JSON payloads."""
import json
from pathlib import Path
import pytest
import httpx
from agent.task_intent import classify_task
from brain.understanding import SYSTEM,parse_understanding
from router.config import Config,Provider,Model
from router.engine import Engine
from brain.coordinator import Brain
from brain.state import TaskStore
from types import SimpleNamespace
from unittest.mock import AsyncMock
from agent import orchestrator

PROJECT_REQUEST='''برق، عاوزك تبنيلي برنامج Windows كامل اسمه TOFU Desktop Buddy.
احفظ الإعدادات في JSON، وممكن تضيف شاشة إعدادات بسيطة.
لا تكتفي بكتابة شرح أو خطوات أعملها أنا. لا تتوقف بمجرد إنشاء ملفات أولية.
لو نموذج AI فشل، حاول استخدام البديل المتاح مع الحفاظ على تقدمك.
اطلب موافقتي على الكتابة والتشغيل الحساس عند الحاجة.
ابدأ التنفيذ الآن، عاوز أشوف البرنامج شغال قدامي.'''


def test_clear_project_goal_survives_rules_and_polite_words():
    intent=classify_task(PROJECT_REQUEST)
    assert intent and intent['kind']=='coding' and intent['new_project']
    assert 'JSON' in intent['goal'] and 'ممكن' in intent['goal']


@pytest.fixture
def actual_engine(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'state'))
    monkeypatch.setattr('core.secrets.get',lambda name:'test-not-a-real-key')
    return Engine(Config(providers=[Provider(name='groq',base_url='https://api.groq.com/openai/v1',api_key_env='GROQ_API_KEY',
        models=[Model(name='openai/gpt-oss-120b',free=True,strengths=['reasoning','coding'],context_window=32000)])]),cache_path=str(tmp_path/'cache.sqlite3'))


def controlled_http(monkeypatch,handler):
    real=httpx.AsyncClient
    def client(**kwargs):
        kwargs['transport']=httpx.MockTransport(handler)
        kwargs['trust_env']=False
        return real(**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',client)


@pytest.mark.asyncio
async def test_internal_understanding_uses_text_models_for_specs_mentioning_json(actual_engine,monkeypatch):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({
            'kind':'coding','goal':'Create TOFU Desktop Buddy','question':'','task':'coding'})}}]})
    controlled_http(monkeypatch,respond)
    result=await actual_engine.run([{'role':'system','content':SYSTEM},
        {'role':'user','content':json.dumps({'current_user_message':PROJECT_REQUEST})}],
        use_cache=False,task_hint='reasoning',response_validator=parse_understanding)
    assert parse_understanding(result['content'])['kind']=='coding'
    assert len(calls)==1 and calls[0].url.host=='api.groq.com'


@pytest.mark.asyncio
async def test_recoverable_json_wrapper_reaches_the_real_contract(actual_engine,monkeypatch):
    body={'kind':'coding','goal':'Change a JSON settings file','question':'','task':'coding'}
    controlled_http(monkeypatch,lambda request:httpx.Response(200,json={'choices':[{'message':{
        'content':'```json\n'+json.dumps(body)+'\n```'}}]}))
    result=await actual_engine.run([{'role':'system','content':SYSTEM},{'role':'user','content':'Change the JSON settings'}],
        use_cache=False,task_hint='reasoning',response_validator=parse_understanding)
    assert parse_understanding(result['content'])==body


@pytest.mark.asyncio
async def test_obvious_project_is_prepared_even_when_no_model_can_connect(tmp_path):
    engine=SimpleNamespace(run=AsyncMock(side_effect=AssertionError('No model needed for initial project creation')))
    brain=Brain(engine,TaskStore(tmp_path/'brain.sqlite3'))
    response=await brain.command([{'role':'user','content':PROJECT_REQUEST}],'project',model='local-only')
    assert response['intent']['new_project']
    prepared=await brain.prepare(str(tmp_path),[{'role':'user','content':'unrelated client text'}],model='local-only',
        conversation_id='project',command_id=response['command_id'])
    try:
        assert prepared['plan']['steps'][0]['tool']=='project_bootstrap'
        assert prepared['task_status']=='awaiting_approval'
        assert 'JSON' in brain.store.get(prepared['task_id'])['goal']
        assert not (tmp_path/'barq-app').exists()
        engine.run.assert_not_called()
    finally:orchestrator.PENDING.pop(prepared['plan_id'],None)


@pytest.mark.asyncio
async def test_provider_failover_uses_actual_router_and_http_adapters(actual_engine,monkeypatch):
    actual_engine.config.providers.append(Provider(name='openrouter',base_url='https://openrouter.ai/api/v1',api_key_env='OPENROUTER_API_KEY',
        models=[Model(name='openrouter/free',free=True,strengths=['reasoning'],context_window=32000)]))
    calls=[]
    def respond(request):
        calls.append(request.url.host)
        if request.url.host=='api.groq.com':return httpx.Response(503,json={'error':'temporarily unavailable'})
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({
            'kind':'coding','goal':'Change the button color','question':'','task':'coding'})}}]})
    monkeypatch.setenv('BARQ_PROVIDER_RETRIES','0')
    controlled_http(monkeypatch,respond)
    brain=Brain(actual_engine,TaskStore(Path(actual_engine.cache.path).parent/'brain.sqlite3'))
    response=await brain.command([{'role':'user','content':'محتاج الزرار ده يبقى أحمر في المشروع'}],'fallback')
    assert response['intent']['kind']=='coding'
    assert set(calls)=={'api.groq.com','openrouter.ai'}
    assert not response.get('pending_command')
    assert not orchestrator.PENDING or all(p.get('workspace')!=str(Path(actual_engine.cache.path).parent) for p in orchestrator.PENDING.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('status,category',[(401,'auth'),(429,'quota'),(503,'provider')])
async def test_outage_persists_cause_and_retry_survives_restart(actual_engine,monkeypatch,tmp_path,status,category):
    monkeypatch.setenv('BARQ_PROVIDER_RETRIES','0')
    working=[False];calls=[]
    def respond(request):
        calls.append(request)
        if not working[0]:return httpx.Response(status,json={'error':'upstream body must never be exposed'})
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({
            'kind':'coding','goal':'Change the requested button color','question':'','task':'coding'})}}]})
    controlled_http(monkeypatch,respond)
    path=tmp_path/'brain.sqlite3';brain=Brain(actual_engine,TaskStore(path))
    text='محتاج الزرار ده يبقى أحمر في المشروع'
    response=await brain.command([{'role':'user','content':text}],'waiting')
    pending=response['pending_command']
    assert pending['diagnostic']['attempts'][0]['code']==category
    assert 'upstream body' not in json.dumps(response)
    assert brain.commands.get(pending['id'],'waiting')['messages'][-1]['content']==text
    with pytest.raises(ValueError,match='another conversation'):
        await brain.command([],'other',command_id=pending['id'])
    # Simulate expiry of the provider cooldown, then restart the coordinator.
    for value in actual_engine.health.data.values():value['cooldown']=0
    clock=actual_engine.network.breaker.clock
    actual_engine.network.breaker.clock=lambda:clock()+120
    working[0]=True;restarted=Brain(actual_engine,TaskStore(path))
    resumed=await restarted.command([],'waiting',command_id=pending['id'])
    assert resumed['intent']['kind']=='coding' and text in resumed['intent']['goal']
    assert resumed['command_id']==pending['id'] and len(calls)==2


@pytest.mark.asyncio
async def test_private_retry_cannot_switch_to_cloud_after_checkpoint_redaction(actual_engine,monkeypatch,tmp_path):
    calls=[]
    controlled_http(monkeypatch,lambda request:calls.append(request) or httpx.Response(500))
    brain=Brain(actual_engine,TaskStore(tmp_path/'brain.sqlite3'))
    secret='private-secret-value-123456'
    response=await brain.command([{'role':'user','content':'محتاج الزرار مختلف. API_KEY='+secret}],'private')
    command_id=response['pending_command']['id']
    assert secret not in (tmp_path/'brain.sqlite3').read_bytes().decode('utf-8',errors='ignore')
    assert brain.commands.get(command_id,'private')['local_only']
    again=await brain.command([],'private',model='groq/openai/gpt-oss-120b',command_id=command_id)
    assert again['pending_command'] and not calls


@pytest.mark.asyncio
async def test_cancelled_intake_does_not_resume_but_new_request_can_start(tmp_path):
    engine=SimpleNamespace(run=AsyncMock(side_effect=RuntimeError('offline')))
    brain=Brain(engine,TaskStore(tmp_path/'brain.sqlite3'))
    messages=[{'role':'user','content':'محتاج الزرار ده يبقى أحمر'}]
    pending=(await brain.command(messages,'cancel'))['pending_command']['id']
    assert brain.cancel('cancel')['cancelled']
    with pytest.raises(ValueError,match='cancelled'):await brain.command([],'cancel',command_id=pending)
    new=(await brain.command(messages,'cancel'))['pending_command']['id']
    assert new!=pending


@pytest.mark.parametrize('message',[
    'هل تقدر تبنيلي برنامج Windows؟',
    'اشرحلي إزاي أبني برنامج Windows',
    'اكتبلي برومبت: ابني برنامج Windows',
    'ترجم: build a Windows application',
])
def test_questions_and_quoted_requests_do_not_authorize_projects(message):
    assert classify_task(message) is None


def test_unified_command_api_binds_the_original_goal_to_preparation(tmp_path,monkeypatch):
    import api
    from fastapi.testclient import TestClient
    engine=SimpleNamespace(run=AsyncMock(side_effect=AssertionError('No cloud classification required')))
    brain=Brain(engine,TaskStore(tmp_path/'brain.sqlite3'))
    monkeypatch.setattr(api,'brain',brain)
    with TestClient(api.app) as client:
        intake=client.post('/v1/brain/command',json={'conversation_id':'api-project','messages':[{'role':'user','content':PROJECT_REQUEST}],'model':'local-only'})
        assert intake.status_code==200
        command_id=intake.json()['command_id']
        wrong=client.post('/v1/agent/prepare',json={'conversation_id':'other','command_id':command_id,'workspace':str(tmp_path),'messages':[{'role':'user','content':'بدّل الهدف'}]})
        assert wrong.status_code==400
        prepared=client.post('/v1/agent/prepare',json={'conversation_id':'api-project','command_id':command_id,'workspace':str(tmp_path),'messages':[{'role':'user','content':'بدّل الهدف'}]})
        assert prepared.status_code==200
        result=prepared.json()
        try:
            assert result['plan']['steps'][0]['tool']=='project_bootstrap'
            assert 'TOFU Desktop Buddy' in brain.store.get(result['task_id'])['goal']
            assert not (tmp_path/'barq-app').exists()
            engine.run.assert_not_called()
        finally:orchestrator.PENDING.pop(result['plan_id'],None)


@pytest.mark.asyncio
async def test_cancellation_during_understanding_cannot_resurrect_the_command(tmp_path):
    import asyncio
    started=asyncio.Event();finish=asyncio.Event()
    async def delayed(*args,**kwargs):
        started.set();await finish.wait()
        return {'content':json.dumps({'kind':'coding','goal':'Change a button','question':'','task':'coding'})}
    brain=Brain(SimpleNamespace(run=delayed),TaskStore(tmp_path/'brain.sqlite3'))
    pending=asyncio.create_task(brain.command([{'role':'user','content':'محتاج اللون مختلف'}],'stop'))
    await started.wait();assert brain.cancel('stop')['cancelled'];finish.set()
    result=await pending
    assert result['source']=='cancelled' and result['intent'] is None


@pytest.mark.asyncio
async def test_routing_preview_never_consumes_recovery_probe(actual_engine,monkeypatch):
    from command_network.contracts import Request
    ident='groq/openai/gpt-oss-120b'
    actual_engine.network.breaker.failure(ident,503)
    clock=actual_engine.network.breaker.clock;actual_engine.network.breaker.clock=lambda:clock()+120
    req=Request(messages=[{'role':'user','content':'Review the selected project'}])
    for _ in range(5):
        _,plan=actual_engine.network.prepare(req)
        assert ident in plan.chain
    assert actual_engine.network.breaker.peek(ident)
    controlled_http(monkeypatch,lambda request:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'kind':'coding','goal':'Review the project'})}}]}))
    result=await actual_engine.run(req.messages,use_cache=False,task_hint='reasoning',response_validator=parse_understanding)
    assert parse_understanding(result['content'])['question']==''
    assert actual_engine.network.breaker.status(ident)=='closed'


@pytest.mark.asyncio
async def test_cancelled_model_dispatch_releases_its_recovery_probe(actual_engine,monkeypatch):
    import asyncio
    started=asyncio.Event();never=asyncio.Event();ident='groq/openai/gpt-oss-120b'
    actual_engine.network.breaker.failure(ident,503)
    clock=actual_engine.network.breaker.clock;actual_engine.network.breaker.clock=lambda:clock()+120
    async def respond(request):
        started.set();await never.wait()
        return httpx.Response(500)
    controlled_http(monkeypatch,respond)
    job=asyncio.create_task(actual_engine.run([{'role':'user','content':'Review the project'}],use_cache=False,
        task_hint='reasoning',response_validator=parse_understanding))
    await asyncio.wait_for(started.wait(),2)
    job.cancel()
    with pytest.raises(asyncio.CancelledError):await job
    assert actual_engine.network.breaker.peek(ident)


def test_understanding_contract_defaults_auxiliary_fields_but_rejects_ambiguity():
    assert parse_understanding('{"kind":"coding","goal":"Change a button"}')['task']=='coding'
    with pytest.raises(ValueError):parse_understanding('{"kind":"coding","kind":"computer","goal":"x"}')
    with pytest.raises(ValueError):parse_understanding('{"kind":"run_command","goal":"x"}')


@pytest.mark.parametrize('wording',[
    'يا برق اعملي برنامج حسابات جديد',
    'برق، عايزك تعملي تطبيق للمبيعات',
    'ممكن تبنيلي برنامج Windows للمخازن',
    'برمجلي تطبيق للمكتب',
    'build a desktop application for inventory',
    'عاوزك تبنيلي برنامج اسمه TOFU Desktop Buddy',
])
def test_goal_classification_is_not_cancelled_by_later_constraints(wording):
    intent=classify_task(wording+'\nلا تكتفي بكتابة شرح. ممكن تضيف زر إعدادات ويحفظ JSON.')
    assert intent and intent['kind']=='coding' and intent['new_project']


@pytest.mark.parametrize('wording',[
    'لا تبني برنامج Windows دلوقتي',
    'ما تعملش برنامج جديد',
    'متغيرش الملف في المشروع',
    'مش عاوزك تعمل البرنامج',
    "don't build a new application",
])
def test_negated_requests_do_not_authorize_the_opposite_action(wording):
    assert classify_task(wording) is None


@pytest.mark.asyncio
async def test_plain_json_output_does_not_require_provider_native_schema_support(actual_engine,monkeypatch):
    controlled_http(monkeypatch,lambda request:httpx.Response(200,json={'choices':[{'message':{'content':'{"color":"red"}'}}]}))
    result=await actual_engine.run([{'role':'user','content':'Return JSON with color red'}],use_cache=False)
    assert json.loads(result['content'])=={'color':'red'}


def test_explicit_native_json_capability_filter_remains_enforced():
    from command_network.contracts import Request,TaskProfile
    from command_network.registry import Capability
    from command_network.routing import DecisionRouter
    req=Request(messages=[{'role':'user','content':'Structured native response'}])
    profile=TaskProfile(task_type='reasoning',needs_json=True,requires_native_json=True)
    plan=DecisionRouter().plan(req,profile,[Capability(id='p/text',provider='p',name='text',supports_json=False),
        Capability(id='p/native',provider='p',name='native',supports_json=True)])
    assert plan.chain==['p/native'] and 'p/text' in plan.rejected


@pytest.mark.asyncio
async def test_identity_words_inside_a_project_goal_do_not_hijack_the_command(tmp_path):
    engine=SimpleNamespace(run=AsyncMock(side_effect=AssertionError('Clear project requires no model')))
    brain=Brain(engine,TaskStore(tmp_path/'brain.sqlite3'))
    response=await brain.command([{'role':'user','content':'ابني برنامج فيه زر مكتوب عليه مين عملك'}],'identity-in-project')
    assert response['intent']['kind']=='coding' and response['intent']['new_project']
    assert not response.get('reply')
    engine.run.assert_not_called()
