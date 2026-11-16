import httpx
class UsageText(str):
    """String-compatible completion with provider-reported billing-free usage metadata."""
    def __new__(cls,value,usage=None,headers=None):
        item=str.__new__(cls,value)
        item.usage=usage if isinstance(usage,dict) else {}
        item.rate_headers=dict(headers or {})
        return item
class ProviderError(Exception):
    def __init__(self,message,status=None,headers=None):super().__init__(message);self.status=status;self.retry_after=(headers or {}).get('retry-after')
async def complete(provider,model,messages,timeout=45,stream=False):
    from providers.reliability import connect_timeout,read_timeout
    from router.config import key_for
    if provider.kind == 'local':
        from providers.ollama import verified_base_url
        verified_base_url(provider.base_url)
    from providers.discovery import validated_chat_url, safe_status
    url=(verified_base_url(provider.base_url)[:-3] + ('/v1/chat/completions' if stream else '/api/chat')) if provider.kind == 'local' else validated_chat_url(provider)
    headers={'Content-Type':'application/json'}
    if provider.kind != 'local':headers['Authorization']='Bearer '+key_for(provider)
    payload={'model':model.name,'messages':messages,'stream':stream}
    # Use conservative sampling for structured agent contracts; do not force
    # JSON mode on providers without an advertised capability.
    structured = (not stream and any(isinstance(msg,dict) and msg.get('role')=='system'
                  and ('Return a SINGLE valid JSON object' in str(msg.get('content',''))
                       or 'Return only JSON:' in str(msg.get('content',''))) for msg in messages))
    if structured and provider.kind != 'local':
        payload['temperature']=0
        payload['max_tokens']=2048
        if getattr(model,'supports_json',False):
            payload['response_format']={'type':'json_object'}
    if provider.kind == 'local':
        from providers.streaming import _ollama_settings
        num_ctx,keep_alive=_ollama_settings(model)
        payload['options']={'num_ctx':num_ctx}
        if structured:
            payload['format']='json'
            payload['options'].update({'temperature':0,'num_predict':2048})
        payload['keep_alive']=keep_alive
        from core.generation import SOURCE_TARGET
        if SOURCE_TARGET.get():
            payload['think']=False
            payload['options'].update({'temperature':0.2,'num_predict':8192})
    client=httpx.AsyncClient(timeout=httpx.Timeout(connect=connect_timeout(provider.kind=='local'),read=read_timeout(timeout,provider.kind=='local'),write=30.0,pool=10.0),trust_env=provider.kind != 'local')
    try:
        if stream:
            # Caller owns the response stream and client lifetime.
            req=client.build_request('POST',url,json=payload,headers=headers)
            resp=await client.send(req,stream=True)
            if resp.status_code>=400:
                body=(await resp.aread())[:1600].decode('utf-8',errors='replace')
                from router.free_policy import note_billing
                billed=note_billing(provider.name,resp.status_code,body)
                await resp.aclose()
                raise ProviderError('مزود الخدمة طلب الدفع وتم إيقافه' if billed else safe_status(resp.status_code)[1],resp.status_code,resp.headers)
            return client,resp
        resp=await client.post(url,json=payload,headers=headers)
        if resp.status_code>=400:
            from router.free_policy import note_billing
            billed=note_billing(provider.name,resp.status_code,resp.text[:1600])
            raise ProviderError('مزود الخدمة طلب الدفع وتم إيقافه' if billed else safe_status(resp.status_code)[1],resp.status_code,resp.headers)
        data=resp.json()
        if provider.kind=='local':
            if data.get('error') or data.get('done') is not True:raise ProviderError('Ollama completion did not finish')
            if SOURCE_TARGET.get() and data.get('done_reason')=='length':
                failure=ValueError('Source generation reached the output limit; request a smaller complete file')
                failure.partial_source=str(data.get('message',{}).get('content',''))[:24000]
                raise failure
            return UsageText(data['message']['content'] or '',
                             {'total_tokens':int(data.get('prompt_eval_count',0))+int(data.get('eval_count',0))},resp.headers)
        return UsageText(data['choices'][0]['message']['content'] or '',data.get('usage'),resp.headers)
    except httpx.HTTPError as exc:
        err=ProviderError('انتهت مهلة انتظار النموذج؛ برق هيجرّب البديل المتاح.' if isinstance(exc,httpx.TimeoutException) else f'Network error ({type(exc).__name__})')
        err.network=isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.NetworkError,httpx.ProxyError,httpx.TimeoutException))
        err.connection_failure=isinstance(exc,(httpx.ConnectError,httpx.ConnectTimeout,httpx.ProxyError))
        raise err from exc
    finally:
        if not stream:await client.aclose()
