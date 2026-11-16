"""Canonical model inventory shared by the model picker and OpenAI-compatible API."""

async def model_inventory(engine):
    await engine.refresh_local()
    from router.config import key_for
    result=[]
    for p in engine.config.providers:
        for m in p.models:
            ident=p.name+'/'+m.name
            from router.quota import quota_key
            from router.free_policy import blocked,permitted
            qkey=quota_key(p,m)
            is_free=p.kind=='local' or (m.free and permitted(p.name,m.name))
            qok=engine.limiter.allowed(qkey,m.rpm or p.rpm,m.rpd or p.rpd,m.tpm or p.tpm,0,m.tpd or p.tpd)
            visible=p.enabled and m.enabled and is_free and not blocked(p.name)
            reason=('المزود متوقف بسبب طلب دفع' if blocked(p.name) else p.disabled_reason_ar or 'المزود غير مفعّل') if not p.enabled or blocked(p.name) else 'النموذج غير مفعّل أو متقاعد' if not m.enabled else 'النموذج غير معتمد مجانًا' if not is_free else 'مفتاح API مش موجود' if not key_for(p) else 'الحصة خلصت مؤقتًا' if not qok else 'النموذج في فترة انتظار بعد خطأ' if not engine.health.available(ident) else ''
            result.append({'id':ident,'provider':p.name,'kind':p.kind,'strengths':m.strengths,
                'context_window':m.context_window,'configured':bool(key_for(p)),'enabled':visible,
                'available':visible and bool(key_for(p)) and engine.health.available(ident) and qok,
                'unavailable_reason':reason,'priority':p.priority,'remaining_today':engine.limiter.remaining(qkey,m.rpd or p.rpd),
                'data_use':m.data_use,'free':is_free,'health':engine.health.snapshot().get(ident)})
    return {'models':result}
