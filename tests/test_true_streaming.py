"""Streaming tests: native chunks, cancellation, fallback and safe error handling."""
import asyncio
import json
import pytest
import httpx
from router.config import Config
from router.engine import Engine
from providers.client import ProviderError
from providers.streaming import stream_complete


def fixture_config(monkeypatch):
    monkeypatch.setenv('STREAM_TEST_KEY','fake-key-for-tests')
    return Config.model_validate({'providers':[
        {'name':'cloudtest','api_key_env':'STREAM_TEST_KEY','base_url':'https://example.invalid/v1',
         'priority':90,'models':[{'name':'alpha','strengths':['coding']},{'name':'beta','strengths':['coding']}]},
        {'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1','priority':20,
         'models':[{'name':'local-coder','strengths':['coding']}]}]})


@pytest.mark.asyncio
async def test_real_incremental_tokens_and_metrics(monkeypatch,tmp_path):
    cfg=fixture_config(monkeypatch)
    import providers.streaming as stream
    ready=asyncio.Event()
    proceed=asyncio.Event()
    async def provider(p,m,messages):
        yield 'first '
        ready.set()
        await proceed.wait()
        yield 'second'
    monkeypatch.setattr(stream,'stream_complete',provider)
    e=Engine(cfg,False,str(tmp_path/'cache.db'))
    gen=e.stream_run([{'role':'user','content':'write python code'}],model='cloudtest/alpha')
    output=[]
    async def collect():
        async for evt in gen:output.append(evt)
    task=asyncio.create_task(collect())
    await asyncio.wait_for(ready.wait(),1)
    assert any(x['type']=='token' and x['content']=='first ' for x in output)
    assert not any(x['type']=='done' for x in output)
    proceed.set()
    await asyncio.wait_for(task,1)
    assert ''.join(x['content'] for x in output if x['type']=='token')=='first second'
    assert [x['type'] for x in output].index('model')<[x['type'] for x in output].index('token')
    assert any(x['type']=='metrics' and x['time_to_first_token_seconds']>=0 for x in output)
    assert output[-1]['type']=='done'


@pytest.mark.asyncio
async def test_fallback_only_before_first_token(monkeypatch,tmp_path):
    cfg=fixture_config(monkeypatch)
    import providers.streaming as stream
    names=[]
    async def provider(p,m,messages):
        names.append(m.name)
        if m.name=='alpha':raise ProviderError('quota',429)
        yield 'backup answer'
    monkeypatch.setattr(stream,'stream_complete',provider)
    e=Engine(cfg,False,str(tmp_path/'cache.db'))
    events=[x async for x in e.stream_run([{'role':'user','content':'write python code'}])]
    assert names[:2]==['alpha','beta']
    model=next(x for x in events if x['type']=='model')
    assert model['model']=='cloudtest/beta'
    assert len(model['attempts'])==1
    assert ''.join(x['content'] for x in events if x['type']=='token')=='backup answer'


@pytest.mark.asyncio
async def test_partial_error_does_not_mix_models(monkeypatch,tmp_path):
    cfg=fixture_config(monkeypatch)
    import providers.streaming as stream
    names=[]
    async def provider(p,m,messages):
        names.append(m.name)
        yield 'partial work'
        raise ProviderError('broken midway')
    monkeypatch.setattr(stream,'stream_complete',provider)
    e=Engine(cfg,False,str(tmp_path/'cache.db'))
    events=[x async for x in e.stream_run([{'role':'user','content':'write python code'}])]
    assert names==['alpha']
    assert [x for x in events if x['type']=='token'][0]['content']=='partial work'
    assert events[-1]['type']=='error' and events[-1]['partial'] is True


@pytest.mark.asyncio
async def test_cancellation_closes_upstream(monkeypatch,tmp_path):
    cfg=fixture_config(monkeypatch)
    import providers.streaming as stream
    closed=asyncio.Event()
    async def provider(p,m,messages):
        try:
            yield 'hello'
            await asyncio.sleep(60)
        finally:
            closed.set()
    monkeypatch.setattr(stream,'stream_complete',provider)
    e=Engine(cfg,False,str(tmp_path/'cache.db'))
    gen=e.stream_run([{'role':'user','content':'write python code'}],model='cloudtest/alpha')
    for _ in range(5):
        item=await gen.__anext__()
        if item['type']=='token':break
    assert item['type']=='token'
    await gen.aclose()
    await asyncio.wait_for(closed.wait(),1)


@pytest.mark.asyncio
async def test_provider_sse_is_upstream_not_simulated(monkeypatch):
    import providers.streaming as stream_module
    from router.config import Provider,Model
    cfg=fixture_config(monkeypatch)
    # Intentional v2.9 security change: cloud hosts must be pinned; this fake
    # host is registered only inside the isolated HTTP MockTransport test.
    import providers.discovery as discovery
    monkeypatch.setitem(discovery.CLOUD_HOSTS,'cloudtest','example.invalid')
    real_client=httpx.AsyncClient
    def transport(request):
        payload=json.loads(request.content)
        assert payload['stream'] is True
        assert request.url.path.endswith('/chat/completions')
        body=('data: '+json.dumps({'choices':[{'delta':{'role':'assistant'}}]})+'\n\n'
              'data: '+json.dumps({'choices':[{'delta':{'content':'actual '}}]})+'\n\n'
              'data: '+json.dumps({'choices':[{'delta':{'content':'tokens'},'finish_reason':'stop'}]})+'\n\n'
              'data: [DONE]\n\n')
        return httpx.Response(200,stream=httpx.ByteStream(body.encode()))
    def fake_client(*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(transport)
        return real_client(*args,**kwargs)
    monkeypatch.setattr(stream_module.httpx,'AsyncClient',fake_client)
    text=[x async for x in stream_complete(cfg.providers[0],cfg.providers[0].models[0],[{'role':'user','content':'hi'}])]
    assert text==['actual ','tokens']


@pytest.mark.asyncio
async def test_api_stream_reflects_metrics(monkeypatch):
    from fastapi.testclient import TestClient
    import api
    async def engine_stream(messages,model='auto',task_hint=None):
        yield {'type':'routing','status':'Selecting…'}
        yield {'type':'model','model':'groq/small','provider':'groq','attempts':[],'offline':False,'cached':False}
        yield {'type':'token','content':'one'}
        yield {'type':'metrics','latency_seconds':.22,'time_to_first_token_seconds':.1,'characters_per_second':14,'output_characters':3}
        yield {'type':'done','finish_reason':'stop'}
    monkeypatch.setattr(api.engine,'stream_run',engine_stream)
    with TestClient(api.app) as client:
        response=client.post('/v1/router/chat/stream',json={'messages':[{'role':'user','content':'hello'}]})
    assert response.status_code==200
    assert 'event: token\ndata: {"content": "one"}' in response.text
    assert 'event: metrics' in response.text
    assert 'time_to_first_token_seconds' in response.text


@pytest.mark.asyncio
async def test_router_stream_reports_partial_without_done(monkeypatch):
    from fastapi.testclient import TestClient
    import api
    async def failing_stream(messages,model='auto',task_hint=None):
        yield {'type':'routing','status':'Connecting'}
        yield {'type':'model','model':'cloudtest/alpha','provider':'cloudtest','attempts':[],'offline':False}
        yield {'type':'token','content':'unfinished'}
        yield {'type':'error','message':'Stream interrupted; partial answer kept','partial':True}
    monkeypatch.setattr(api.engine,'stream_run',failing_stream)
    with TestClient(api.app) as client:
        response=client.post('/v1/router/chat/stream',json={'messages':[{'role':'user','content':'write code'}]})
    assert response.status_code==200
    assert 'event: token' in response.text
    assert 'event: error' in response.text
    assert 'event: done' not in response.text


def test_performance_endpoint_uses_measured_samples(monkeypatch):
    from fastapi.testclient import TestClient
    import api
    monkeypatch.setattr(api.engine,'stats',[
        {'model':'ollama/test','attempts':['cloud: 429'],
         'metrics':{'time_to_first_token_seconds':.42,'latency_seconds':1.4}},
        {'model':'gemini/test','attempts':[],
         'metrics':{'time_to_first_token_seconds':.21,'latency_seconds':.8}},
    ])
    with TestClient(api.app) as client:
        d=client.get('/v1/performance').json()
    assert d['measured_responses']==2
    assert d['fallback_responses']==1
    assert d['ttft_seconds']['p95']>=0
    assert d['recent_models']==['ollama/test','gemini/test']


@pytest.mark.asyncio
async def test_empty_chunks_share_the_first_response_deadline():
    from router.engine import _first_stream_piece

    async def provider():
        yield ''
        await asyncio.Event().wait()

    upstream = provider()
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(_first_stream_piece(upstream, 0.02), timeout=0.5)
    finally:
        await upstream.aclose()
