import asyncio
import pytest
from pydantic import ValidationError
from command_network.contracts import Request,TaskGraph
from command_network.triage import Triage
from command_network.routing import DecisionRouter
from command_network.registry import Capability
from command_network.control import CircuitBreaker,Quota
from command_network.cache import ExactCache
from command_network.planner import schedule
from command_network.verifier import verify

MODEL=lambda id,provider='groq',kind='cloud',**fields:Capability(id=id,provider=provider,name=id.split('/')[-1],kind=kind,configured=True,**fields)

def test_contract_rejects_empty_invalid_messages():
    with pytest.raises(ValidationError):Request(messages=[])
    with pytest.raises(ValidationError):Request(messages=[{'role':'admin','content':'hello'}])
    with pytest.raises(ValidationError):Request(messages=[{'role':'user','content':123}])

def test_arabic_triage_and_code_intent():
    triage=Triage()
    assert triage.classify(Request(messages=[{'role':'user','content':'ترجم الفقرة دي'}])).task_type=='translation'
    assert triage.classify(Request(messages=[{'role':'user','content':'فيه خطأ traceback في main.py'}])).task_type=='debugging'
    assert triage.classify(Request(messages=[{'role':'user','content':'اكتب كود بايثون'}])).task_type=='coding'
    assert triage.classify(Request(messages=[{'role':'user','content':'لخص المستند report.pdf'}])).task_type=='long_document'
    image=Request(messages=[{'role':'user','content':'ايه في الصورة دي'}],attachments=[{'type':'image/png'}])
    assert triage.classify(image).task_type=='vision'

def test_sensitive_forces_local_and_filters_unavailable():
    req=Request(messages=[{'role':'user','content':'My email: person@example.com'}],privacy='local-only')
    profile=Triage().classify(req)
    chain=DecisionRouter(random_source=lambda:1).plan(req,profile,[MODEL('c/a'),MODEL('ollama/local',provider='ollama',kind='local')])
    assert chain.chain==['ollama/local']
    assert chain.rejected['c/a']=='privacy: local-only'
    assert Triage.privacy_required(req)

def test_reject_vision_and_context_hard_filters():
    req=Request(messages=[{'role':'user','content':'اشرح الصورة'}],attachments=[{'type':'image/png'}])
    prof=Triage().classify(req)
    plan=DecisionRouter(random_source=lambda:1).plan(req,prof,[MODEL('p/t'),MODEL('p/v',modalities=['text','image'])])
    assert plan.chain==['p/v']
    assert 'p/t' in plan.rejected
    req2=Request(messages=[{'role':'user','content':'x'*5000}])
    prof2=Triage().classify(req2)
    p2=DecisionRouter(random_source=lambda:1).plan(req2,prof2,[MODEL('p/small',context_window=1000)])
    assert p2.chain==[] and p2.rejected['p/small']=='insufficient context'

def test_fallback_provider_diversity_and_ollama_last():
    req=Request(messages=[{'role':'user','content':'Hello'}]);prof=Triage().classify(req)
    models=[MODEL('a/1',provider='a',p50_latency=.1),MODEL('a/2',provider='a',p50_latency=.2),MODEL('b/1',provider='b',p50_latency=.3),MODEL('ollama/3',provider='ollama',kind='local',p50_latency=.01)]
    p=DecisionRouter(random_source=lambda:1).plan(req,prof,models)
    assert p.chain[-1]=='ollama/3'
    assert [x.split('/')[0] for x in p.chain[:3]]==['a','b','a']

def test_control_circuit_and_quota():
    tm=[100.]
    breaker=CircuitBreaker(clock=lambda:tm[0],cooldown=10,threshold=2)
    breaker.failure('x');assert breaker.allowed('x')
    breaker.failure('x');assert not breaker.allowed('x')
    tm[0]+=11;assert breaker.allowed('x');assert not breaker.allowed('x')
    breaker.success('x');assert breaker.allowed('x')
    tm2=[100000.];quota=Quota(clock=lambda:tm2[0],margin=0)
    quota.record('x',10);assert not quota.allowed('x',rpm=1)
    tm2[0]+=61;assert quota.allowed('x',rpm=1)

def test_dag_reject_cycles_and_depth():
    with pytest.raises(ValidationError):TaskGraph(nodes=[dict(id='A',goal='a',task_type='qa',depends_on=['B']),dict(id='B',goal='b',task_type='qa',depends_on=['A'])])
    with pytest.raises(ValidationError):TaskGraph(nodes=[dict(id=str(i)+'a',goal='a',task_type='qa',depends_on=[str(i-1)+'a'] if i else []) for i in range(5)])

@pytest.mark.asyncio
async def test_dag_parallel_ready_steps():
    g=TaskGraph(nodes=[dict(id='a',goal='A',task_type='qa'),dict(id='b',goal='B',task_type='qa'),dict(id='c',goal='C',task_type='qa',depends_on=['a','b'])])
    async def run(node,inputs):return node.goal+str(len(inputs))
    assert await schedule(g,run)=={'a':'A0','b':'B0','c':'C2'}

@pytest.mark.asyncio
async def test_cache_coalesces_identical_inflight():
    cache=ExactCache();count=0
    async def call():
        nonlocal count;count+=1;await asyncio.sleep(.02);return 'success'
    a,b=await asyncio.gather(cache.coalesce('x',call),cache.coalesce('x',call))
    assert a==b=='success' and count==1

def test_verifier_json_and_language():
    p=Triage().classify(Request(messages=[{'role':'user','content':'رد JSON بالعربي'}]))
    assert not verify('not JSON',p).accepted
    assert verify('{"ok":1}',p).accepted

def test_benchmark_five_offline_cases():
    from scripts.barq_network_benchmark import run
    results=run()
    assert len(results)==5
    assert all(x['first_model'] for x in results)

def test_network_endpoints_report_no_secret_text():
    from fastapi.testclient import TestClient
    from api import app
    with TestClient(app) as client:
        response=client.post('/v1/brain/route-preview',json={'messages':[{'role':'user','content':'اشرح معنى الذكاء الاصطناعي'}]})
        assert response.status_code==200
        data=response.json()
        assert data['route']['profile']['language']=='ar'
        rid=data['route']['request_id']
        detail=client.get('/v1/brain/trace/'+rid)
        assert detail.status_code==200
        assert 'اشرح معنى الذكاء' not in detail.text
        mapping=client.get('/v1/brain/network/map')
        assert mapping.status_code==200 and 'models' in mapping.json()

def test_network_intake_rejects_non_messages():
    from fastapi.testclient import TestClient
    from api import app
    with TestClient(app) as client:
        response=client.post('/v1/brain/network/events',json={'messages':[]})
        assert response.status_code==400


def test_common_credentials_and_arabic_password_labels_use_local_routing():
    for text in (
        'Authorization: Bearer sample-token-000',
        'كلمة المرور: sample-password',
        '-----BEGIN OPENSSH PRIVATE KEY-----',
        'github_pat_' + 'a' * 24,
    ):
        request = Request(messages=[{'role': 'user', 'content': text}])
        assert Triage.privacy_required(request)
        assert not Triage.cacheable(request)
