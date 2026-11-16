"""Real, cancellable OpenAI-compatible provider streaming.

Only the configured provider endpoint receives the request. The owner of this
async generator owns the HTTP connection; cancelling iteration closes it.
"""
import json
import os
from typing import AsyncIterator

import httpx

from providers.client import ProviderError
from router.config import key_for


MAX_EVENT_BYTES = 1024 * 1024


def _extract_text(data: dict) -> str:
    choices = data.get('choices') or []
    if not choices:
        return ''
    delta = choices[0].get('delta') or {}
    content = delta.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(part.get('text', '') for part in content
                       if isinstance(part, dict) and part.get('type') == 'text'
                       and isinstance(part.get('text'), str))
    return ''


def _ollama_settings(model=None):
    """Conservative context and idle retention; no hidden model downloads."""
    import re
    from core.adaptive_resources import resources
    num_ctx=resources.ollama_context(model)
    keep_alive = os.getenv('OLLAMA_KEEP_ALIVE', '10m')
    if not re.fullmatch(r'(?:0|[1-9][0-9]*[smh])', keep_alive):
        keep_alive = '10m'
    return num_ctx, keep_alive


async def _ollama_stream(provider, model, messages, timeout) -> AsyncIterator[str]:
    """Native Ollama NDJSON streaming supports keep_alive and num_ctx."""
    from providers.ollama import verified_base_url
    url = verified_base_url(provider.base_url)[:-3] + '/api/chat'
    num_ctx, keep_alive = _ollama_settings(model)
    payload = {'model':model.name, 'messages':messages, 'stream':True,
               'keep_alive':keep_alive, 'options':{'num_ctx':num_ctx}}
    from core.generation import SOURCE_TARGET
    if SOURCE_TARGET.get():
        payload['think']=False
        payload['options'].update({'temperature':0.2,'num_predict':8192})
    finished = False
    emitted = False
    try:
        from providers.reliability import connect_timeout,read_timeout
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=connect_timeout(True),read=read_timeout(timeout,True),write=30.0,pool=10.0),trust_env=False) as client:
            async with client.stream('POST',url,json=payload) as response:
                if response.status_code>=400:
                    detail=(await response.aread())[:350].decode(errors='replace')
                    raise ProviderError(f'Ollama HTTP {response.status_code}: {detail}',response.status_code)
                async for line in response.aiter_lines():
                    if not line:continue
                    if len(line.encode('utf-8'))>MAX_EVENT_BYTES:
                        raise ProviderError('Ollama returned an oversized response')
                    try:data=json.loads(line)
                    except ValueError as exc:raise ProviderError('Ollama returned invalid NDJSON') from exc
                    if data.get('error'):raise ProviderError('Ollama: '+str(data['error'])[:250])
                    fragment=data.get('message',{}).get('content','')
                    if isinstance(fragment,str) and fragment:
                        emitted=True
                        yield fragment
                    if data.get('done'):
                        if SOURCE_TARGET.get() and data.get('done_reason')=='length':
                            raise ValueError('Source generation reached the output limit; request a smaller complete file')
                        finished=True
                        break
                if not emitted:raise ProviderError('Ollama returned an empty response')
                if not finished:raise ProviderError('Ollama stream stopped before completion')
    except httpx.HTTPError as exc:
        err=ProviderError(f'Ollama connection problem ({type(exc).__name__})')
        err.network=isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.NetworkError,httpx.TimeoutException,httpx.RemoteProtocolError))
        raise err from exc


async def stream_complete(provider, model, messages, *, timeout=55.0) -> AsyncIterator[str]:
    if provider.kind == 'local':
        async for piece in _ollama_stream(provider, model, messages, timeout):
            yield piece
        return
    from providers.discovery import validated_chat_url, safe_status
    url = validated_chat_url(provider)
    headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
    if provider.kind != 'local':
        headers['Authorization'] = 'Bearer ' + key_for(provider)
    payload = {'model': model.name, 'messages': messages, 'stream': True}
    from providers.reliability import connect_timeout,read_timeout
    limits = httpx.Timeout(read_timeout(timeout), connect=connect_timeout())
    try:
        async with httpx.AsyncClient(timeout=limits, trust_env=provider.kind != 'local') as client:
            async with client.stream('POST', url,
                                     json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    from router.free_policy import note_billing
                    body=(await response.aread())[:1600].decode('utf-8',errors='replace')
                    billed=note_billing(provider.name,response.status_code,body)
                    raise ProviderError('مزود الخدمة طلب الدفع وتم إيقافه' if billed else safe_status(response.status_code)[1],response.status_code,response.headers)
                buffer = ''
                # Some compatible servers ignore stream=true. Show their actual
                # complete response once; never animate fabricated token timing.
                if 'application/json' in response.headers.get('content-type',''):
                    raw=await response.aread()
                    if len(raw)>MAX_EVENT_BYTES:raise ProviderError('Provider response too large')
                    try:content=json.loads(raw)['choices'][0]['message']['content']
                    except (ValueError,KeyError,IndexError,TypeError) as exc:raise ProviderError('Invalid complete response') from exc
                    if not isinstance(content,str) or not content:raise ProviderError('Empty complete response')
                    yield content
                    return
                emitted = False
                saw_done = False
                async for line in response.aiter_lines():
                    if len(line.encode('utf-8')) > MAX_EVENT_BYTES:
                        raise ProviderError('Provider sent an oversized streaming event')
                    if not line or line.startswith(':'):
                        continue
                    if not line.startswith('data:'):
                        continue
                    value = line[5:].strip()
                    if value == '[DONE]':
                        saw_done = True
                        break
                    try:
                        item = json.loads(value)
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise ProviderError('Provider returned invalid streaming JSON') from exc
                    if isinstance(item, dict) and item.get('error'):
                        from router.free_policy import note_billing
                        if note_billing(provider.name,None,str(item.get('error'))):
                            raise ProviderError('مزود الخدمة طلب الدفع وتم إيقافه',402)
                        raise ProviderError('Provider reported an error during streaming')
                    if not isinstance(item, dict):
                        continue
                    text = _extract_text(item)
                    if text:
                        emitted = True
                        yield text
                    if (item.get('choices') or [{}])[0].get('finish_reason'):
                        saw_done = True
                if not emitted:
                    raise ProviderError('Provider produced no text during streaming')
                if not saw_done:
                    # A broken connection after partial output is not a completed answer.
                    raise ProviderError('Provider stream stopped before completion')
    except httpx.HTTPError as exc:
        err = ProviderError(f'Connection problem ({type(exc).__name__})')
        err.network = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError,
                                       httpx.ProxyError, httpx.TimeoutException, httpx.RemoteProtocolError))
        # A ReadTimeout is provider-specific slowness, not proof the whole internet is offline.
        err.connection_failure = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError))
        raise err from exc
