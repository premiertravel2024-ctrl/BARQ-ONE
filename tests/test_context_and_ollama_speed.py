import json
import pytest
import httpx
from router.context import select_context
from router.config import Config


# Each expected value belongs to a specified machine/profile. A release test
# must never inherit live Windows memory pressure, saved profile or .env values.
@pytest.fixture(params=[
    pytest.param((.5,5,'balanced','8192',65536,2048),id='low-ram-2048'),
    pytest.param((2,5,'balanced','8192',65536,4096),id='limited-ram-4096'),
    pytest.param((16,5,'balanced','8192',65536,8192),id='balanced-8192'),
    pytest.param((16,90,'performance','32768',65536,4096),id='busy-cpu-4096'),
    pytest.param((16,5,'eco','32768',65536,4096),id='eco-4096'),
    pytest.param((16,5,'performance','32768',65536,16384),id='performance-16384'),
    pytest.param((16,5,'balanced','4096',65536,4096),id='explicit-upper-bound-4096'),
    pytest.param((16,5,'balanced','8192',1024,1024),id='small-model-1024'),
])
def ollama_budget(monkeypatch,request):
    from core.adaptive_resources import resources
    ram_gib,cpu,mode,configured,model_limit,expected=request.param
    monkeypatch.setenv('OLLAMA_NUM_CTX',configured)
    monkeypatch.setenv('OLLAMA_KEEP_ALIVE','10m')
    monkeypatch.setattr(resources,'snapshot',lambda **kwargs:{
        'ram_available_bytes':int(ram_gib*1024**3),'cpu_load_percent':cpu,
        'logical_cpu_cores':4,'mode':mode,
    })
    return model_limit,expected


def test_context_keeps_system_and_latest_user():
    messages=[{'role':'system','content':'Follow project rules'},*[
        {'role':'user' if i%2==0 else 'assistant','content':('old unrelated notes '*80)+str(i)}
        for i in range(45)],{'role':'user','content':'Fix specific Qwen code parser'}]
    selected,omitted=select_context(messages,4096)
    assert omitted>0
    assert selected[0]==messages[0]
    assert selected[-1]==messages[-1]
    assert sum(len(m['content']) for m in selected)<sum(len(m['content']) for m in messages)
    assert selected==[m for m in messages if m in selected]


def test_context_returns_original_when_short():
    values=[{'role':'user','content':'hello'}]
    selected,omitted=select_context(values,8192)
    assert selected is values and omitted==0


@pytest.mark.asyncio
async def test_ollama_native_stream_has_keep_alive_and_context(monkeypatch,ollama_budget):
    import providers.streaming as streaming
    model_limit,expected=ollama_budget
    config=Config.model_validate({'providers':[{'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1',
                                               'models':[{'name':'qwen:7b','context_window':model_limit}]}]})
    calls=[]
    def transport(req):
        data=json.loads(req.content)
        assert req.url.host=='127.0.0.1' and req.url.path=='/api/chat'
        assert data['keep_alive']=='10m'
        assert data['options']['num_ctx']==expected
        assert data['stream'] is True
        calls.append(data)
        return httpx.Response(200,text='{"message":{"content":"local "},"done":false}\n{"message":{"content":"reply"},"done":false}\n{"done":true}\n')
    real=httpx.AsyncClient
    def mocked(*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(transport)
        return real(*args,**kwargs)
    monkeypatch.setattr(streaming.httpx,'AsyncClient',mocked)
    result=[x async for x in streaming.stream_complete(config.providers[0],config.providers[0].models[0],[{'role':'user','content':'hi'}])]
    assert result==['local ','reply'] and len(calls)==1


@pytest.mark.asyncio
async def test_ollama_native_stream_rejects_truncated_result(monkeypatch):
    import providers.streaming as streaming
    cfg=Config.model_validate({'providers':[{'name':'ollama','kind':'local','base_url':'http://127.0.0.1:11434/v1','models':[{'name':'tiny'}]}]})
    from providers.client import ProviderError
    real=httpx.AsyncClient
    def mocked(*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(lambda req:httpx.Response(200,text='{"message":{"content":"partial"},"done":false}\n'))
        return real(*args,**kwargs)
    monkeypatch.setattr(streaming.httpx,'AsyncClient',mocked)
    seen=[]
    with pytest.raises(ProviderError,match='before completion'):
        async for part in streaming.stream_complete(cfg.providers[0],cfg.providers[0].models[0],[{'role':'user','content':'hi'}]):
            seen.append(part)
    assert seen==['partial']


def test_local_context_never_exceeds_native_ollama_num_ctx(ollama_budget):
    from router.context import effective_window
    from router.config import Provider
    from providers.streaming import _ollama_settings
    model_limit,expected=ollama_budget
    provider=Provider.model_validate({'name':'ollama','kind':'local','base_url':'http://localhost:11434/v1',
                                      'models':[{'name':'local','context_window':model_limit}]})
    model=provider.models[0]
    assert effective_window(provider,model)==expected
    assert _ollama_settings(model)[0]==expected
