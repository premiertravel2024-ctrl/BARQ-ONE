"""Regressions for Windows DNS failure and BARQ repeating the user's greeting."""
import asyncio
import socket
from types import SimpleNamespace

import pytest
from core.addressing import casual_greeting_reply
from brain.coordinator import Brain
from voice.live import live_error, _RetriableLiveConnect


@pytest.mark.parametrize('message', [
    'إزيك يا عم برق؟', 'ازيك ياعم برق', 'ازيك يا برق',
    'عامل إيه يا برق', 'صباح الخير', 'السلام عليكم',
])
def test_direct_greetings_are_not_parroted(message):
    brain=object.__new__(Brain)
    response=brain._local_reply([{'role':'user','content':message}])
    assert response and response != message
    assert 'يا صاحبي' in response


@pytest.mark.parametrize('message',[
    'ازيك يا عم برق افتح البرنامج', 'إزيك يا عم برق، اكتبلي برنامج',
    'عامل إيه يا برق وبعدين راجع المشروع', 'قولي إزيك يا برق بالإنجليزي',
])
def test_action_requests_are_not_swallowed_by_greetings(message):
    assert casual_greeting_reply(message) is None


def test_response_echo_is_rejected_without_rejecting_requested_quotes():
    brain=object.__new__(Brain)
    with pytest.raises(ValueError,match='echoed'):
        brain._check_reply('إزيك يا عم برق؟',[{'role':'user','content':'إزيك يا عم برق؟'}])
    brain._check_reply('تمام يا صاحبي، إنت عامل إيه؟',[{'role':'user','content':'إزيك يا عم برق؟'}])
    brain._check_reply('أهلاً',[{'role':'user','content':'اكتب نص رسالة: أهلاً'}])


def test_dns_error_is_not_mislabeled_as_quota_or_incorrect_key():
    try:
        try:raise socket.gaierror(-2,'Name or service not known')
        except socket.gaierror as cause:raise OSError('Gemini handshake failed') from cause
    except OSError as exc:
        error=live_error(exc)
    assert error['code']=='dns_unavailable'
    assert 'DNS' in error['message']
    assert 'حصة' not in error['message']
    assert 'مفتاح' not in error['message']
    assert live_error(TimeoutError('timed out'))['code']=='network_timeout'


@pytest.mark.asyncio
async def test_dns_retry_connects_on_second_try_without_stream_replay():
    attempts=[]
    class Session:
        async def __aenter__(self):
            attempts.append('connect')
            if len(attempts)==1:raise socket.gaierror(-2,'cannot resolve')
            return 'connected'
        async def __aexit__(self,*args):
            attempts.append('closed')
    client=SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kwargs:Session())))
    async with _RetriableLiveConnect(client,{}) as value:
        assert value=='connected'
    assert attempts==['connect','connect','closed']


@pytest.mark.asyncio
async def test_dns_retry_stops_after_second_failure():
    attempts=[]
    class Session:
        async def __aenter__(self):
            attempts.append(1)
            raise socket.gaierror(-2,'cannot resolve')
        async def __aexit__(self,*args):pass
    client=SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kwargs:Session())))
    with pytest.raises(socket.gaierror):
        async with _RetriableLiveConnect(client,{}):pass
    assert len(attempts)==2


def test_actual_chat_endpoints_reply_to_greeting_without_provider(monkeypatch):
    from fastapi.testclient import TestClient
    import api

    async def never_call(*args,**kwargs):
        raise AssertionError('A direct greeting should not require any cloud/local model')

    monkeypatch.setattr(api.engine,'run',never_call)
    message={'messages':[{'role':'user','content':'إزيك يا عم برق؟'}]}
    with TestClient(api.app) as client:
        router=client.post('/v1/router/chat',json=message)
        assert router.status_code==200 and 'إنت عامل إيه' in router.json()['content']
        completion=client.post('/v1/chat/completions',json=message)
        assert completion.status_code==200
        assert 'إنت عامل إيه' in completion.json()['choices'][0]['message']['content']
        stream=client.post('/v1/router/chat/stream',json=message)
        assert stream.status_code==200
        assert 'إنت عامل إيه' in stream.text
        assert 'event: done' in stream.text


def test_live_websocket_surfaces_dns_failure_instead_of_quota(monkeypatch):
    """Real server WebSocket endpoint, simulated Gemini DNS outage, no internet."""
    import sys
    import types
    from fastapi.testclient import TestClient
    import api
    import google

    attempts=[]
    class BadConnect:
        async def __aenter__(self):
            attempts.append(1)
            raise socket.gaierror(-2,'DNS failed')
        async def __aexit__(self,*args):pass
    class FakeClient:
        def __init__(self,**kwargs):
            self.aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **kwargs:BadConnect()),aclose=self.close)
        async def close(self):pass
    fake_genai=types.ModuleType('google.genai')
    fake_genai.Client=FakeClient
    fake_genai.types=SimpleNamespace()
    monkeypatch.setitem(sys.modules,'google.genai',fake_genai)
    monkeypatch.setattr(google,'genai',fake_genai,raising=False)
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    monkeypatch.setattr('voice.live.gemini_key',lambda:'dummy')
    with TestClient(api.app).websocket_connect('/v1/voice/live') as ws:
        event=ws.receive_json()
        assert event['type']=='error'
        assert event['code']=='dns_unavailable'
        assert 'DNS' in event['message']
        assert 'dummy' not in str(event)
    assert len(attempts)==2
