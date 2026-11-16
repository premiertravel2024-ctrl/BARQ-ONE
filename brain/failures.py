"""Actionable failure categories. Never expose exception bodies, URLs or keys."""
import re

MESSAGES={
    'auth':'مفتاح المزود مرفوض أو صلاحياته غير كافية؛ راجع المفتاح في إدارة النماذج.',
    'quota':'حصة المزود أو معدل الطلبات انتهى مؤقتًا؛ اختار بديلًا أو انتظر تجدد الحصة.',
    'billing':'المزود طلب دفعًا وتم إيقافه؛ استخدم بديلًا مجانيًا مهيّأ.',
    'network':'تعذّر الاتصال بالمزود أو انتهت المهلة؛ راجع الاتصال أو استخدم نموذجًا محليًا متاحًا.',
    'format':'رد النموذج لم يطابق عقد المهمة؛ يمكن إعادة التخطيط بنموذج آخر.',
    'model_missing':'المزود لا يتيح اسم النموذج المحدد؛ اختبر النماذج المتاحة في إدارة النماذج.',
    'no_model':'لا يوجد نموذج مؤهل حاليًا؛ راجع المفاتيح وتفعيل النماذج والحصة والوضع المحلي.',
    'provider':'المزود متوقف مؤقتًا؛ البدائل المتاحة لم تُرجع نتيجة صالحة.',
    'missing_key':'المزود المفعّل يحتاج مفتاح API محفوظًا؛ أضفه من إدارة النماذج.',
    'cooldown':'النماذج في فترة انتظار بعد خطأ سابق؛ انتظر انتهاء الفترة أو اختار بديلًا متاحًا.',
    'local_missing':'الوضع المحلي مطلوب، ولا يوجد نموذج Ollama متاح؛ شغّل Ollama بنموذج منزل بالفعل.',
}


def diagnose(exc):
    attempts=getattr(exc,'attempts',None) or (['No installed Ollama model'] if str(exc).startswith('No installed Ollama model') else [type(exc).__name__])
    rows=[]
    for raw in attempts[:8]:
        text=str(raw).lower()
        code=('billing' if re.search(r'402|payment|billing|دفع',text) else
            'auth' if re.search(r'401|403|credential|api key',text) else
            'quota' if re.search(r'429|quota|rate.limit',text) else
            'network' if re.search(r'network|connect|timeout|مهلة|اتصال',text) else
            'format' if re.search(r'json|contract|structured|schema|format|understanding',text) else
            'model_missing' if '404' in text else
            'no_model' if re.search(r'eligible|ollama|no.*model',text) else 'provider')
        prefix=str(raw).split(':',1)[0]
        model=prefix if re.fullmatch(r'[A-Za-z0-9_./-]{1,180}',prefix) and '/' in prefix else ''
        row={'model':model,'code':code,'message':MESSAGES[code]}
        if row not in rows:rows.append(row)
    diagnostic={'code':rows[0]['code'],'summary':'الطلب محفوظ، والخطوة الحالية متوقفة بسبب خدمة النماذج.',
        'attempts':rows,'actions':['استكمل الطلب المحفوظ بعد عودة النموذج.','افتح إدارة النماذج لمعرفة المفتاح والحصة والنماذج المتاحة.']}
    details=getattr(exc,'diagnostics',{})
    if isinstance(details,dict):
        diagnostic['routing_mode']=details.get('mode','auto')
        reasons=set(details.get('rejected',{}).values())-{'disabled or draining'}
        if rows[0]['code']=='no_model':
            code='local_missing' if details.get('mode')=='local' else 'cooldown' if reasons & {'existing health circuit open','circuit breaker open'} else 'quota' if 'quota exhausted' in reasons else 'missing_key' if reasons=={'missing provider credentials or local model'} else 'no_model'
            rows[0]={**rows[0],'code':code,'message':MESSAGES[code]}
            diagnostic['code']=code
        diagnostic['retry_after_seconds']=max(0,min(600,int(details.get('retry_after_seconds',0))))
        # Values originate in the application router, never upstream response bodies.
        diagnostic['rejected']=[{'model':key,'reason':reason} for key,reason in list(details.get('rejected',{}).items())[:12]]
    return diagnostic
