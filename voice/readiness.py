"""Read-only, local readiness for BARQ's independent voice assistant.

No network probes, privilege escalation or automatic enabling. Inspired by
OpenJarvis's capability-resolution approach, kept inside BARQ policy.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

_CAPS={
 'windows':('Windows','التحكم الصوتي في البرامج متاح على Windows 10/11 فقط.','شغّل برق على Windows.'),
 'computer_control':('التحكم في الكمبيوتر','صلاحية التحكم الرئيسية مش مفعّلة.','الإعدادات ← التحكم في الكمبيوتر ← تفعيل.'),
 'voice_permission':('إذن أوامر برق الصوتي','إذن الأوامر الصوتية المستقلة مش مفعّل.','الإعدادات ← برق الصوتي ← السماح بأوامر الكمبيوتر.'),
 'gemini':('Gemini Live','مفتاح Gemini Live مش موجود أو الوضع المحلي فقط مفعّل.','أضف مفتاح Gemini من إعدادات النماذج؛ صحة الحصة تحتاج اتصالًا حقيقيًا.'),
 'microphone':('مستمع الميكروفون','مستمع الخلفية متوقف؛ المكالمة اليدوية ممكن تشتغل مستقلة عنه.','شغّل الاستماع من إعدادات برق الصوتي واختار الميكروفون.'),
 'local_planner':('نموذج التخطيط المحلي','مفيش نموذج Ollama محلي متأكد من جاهزيته؛ المهام المعقدة ممكن تقف.','ثبّت نموذجًا مجانيًا مناسبًا في Ollama وتأكد إنه ظاهر في برق.'),
 'device_index':('فهرس الجهاز','فهرسة الملفات غير مفعّلة، أو بتتجهز، أو بدون مجلدات مسموح بها.','اسمح بفهرسة المجلد المطلوب، وافتح حالة الفهرسة.'),
 'windows_mcp':('Windows MCP','Windows-MCP مش ظاهر في المسارات المعروفة.','ثبّت Windows-MCP واربطه بإعدادات أدوات برق.'),
}


def _probe() -> dict:
    from voice.gemini import gemini_key
    from voice.wake import wake_preferences, wake_status
    from computer_control.api import load_policy
    from services import device_index
    from voice.offline import local_stt_ready
    try:policy=load_policy()
    except (OSError,ValueError):policy=None
    try:wake=wake_preferences()
    except (OSError,ValueError):wake={}
    try:running=wake_status().get('running',False)
    except (OSError,ValueError,TypeError):running=False
    try:index=device_index.status()
    except (OSError,ValueError,TypeError):index={}
    installed_mcp=shutil.which('windows-mcp') or (Path.home()/'.local'/'bin'/'windows-mcp.exe').is_file()
    # A configured/local-only model is not necessarily LOADED. Report unknown
    # until a true manager check (avoid unprompted Ollama networking).
    local_planner=bool(shutil.which('ollama'))
    return {'windows':sys.platform=='win32','computer_control':bool(policy and policy.enabled),
        'voice_permission':bool(wake.get('wake_computer_enabled')),
        'gemini':bool(gemini_key()) and os.getenv('LOCAL_ONLY','').lower() not in ('1','true','yes'),
        'microphone':bool(running),'local_planner':local_planner,
        'device_index':bool(index.get('settings',{}).get('enabled') and index.get('status')=='ready' and index.get('entries',0)>0),
        'windows_mcp':bool(installed_mcp),'local_stt':bool(local_stt_ready())}


def report(*, probes:dict|None=None) -> dict:
    checks=_probe() if probes is None else dict(probes)
    result=[]
    for key,(label,reason,fix) in _CAPS.items():
        ready=checks.get(key) is True
        result.append({'id':key,'label':label,'ready':ready,
            'state':'ready' if ready else 'blocked',
            'reason':'جاهز من ناحية الإعدادات؛ لم يتم تنفيذ اختبار مباشر.' if ready else reason,
            'fix':None if ready else fix})
    return {'status':'ready' if all(x['ready'] for x in result) else 'needs_setup',
            'capabilities':result,'local_stt_ready':checks.get('local_stt') is True,
            'note':'الفحص محلي فقط، لا يتحقق من ميكروفون حقيقي أو صلاحية Google أو نجاح أوامر Windows.'}


def self_test(*, facts=None, search=None) -> dict:
    """User-initiated safe test; no cloud/mic/actions. Report unverified as such."""
    from voice.utility_tools import local_clock
    checks=[{'name':'local_clock','status':'pass' if local_clock()['status']=='ok' else 'fail'}]
    try:
        fn=facts
        if fn is None:
            from core.windows_facts import answer
            fn=answer
        value=fn('الرام ونسخة Windows')
        checks.append({'name':'system_facts','status':'pass' if value else 'not_verified',
                       'reason':'' if value else 'لم تصل معلومات نظام مؤكدة.'})
    except (OSError,RuntimeError,ValueError):
        checks.append({'name':'system_facts','status':'not_verified','reason':'معلومات الجهاز مش متاحة من بيئة الاختبار.'})
    with tempfile.TemporaryDirectory(prefix='barq-voice-probe-') as temp:
        file=Path(temp)/'barq_voice_readiness_probe.txt'
        file.write_text('BARQ local test only',encoding='utf-8')
        try:
            fn=search
            if fn is None:
                from services.device_index import search as device_search
                fn=device_search
            result=fn('barq_voice_readiness_probe',limit=5)
            hits=result.get('results',[]) if isinstance(result,dict) else []
            actual=any(item.get('name')==file.name for item in hits if isinstance(item,dict))
            checks.append({'name':'device_index_temp','status':'pass' if actual else 'not_verified',
                'reason':'' if actual else 'الملف المؤقت خارج جذور الفهرسة المصرّح بها؛ مفيش إثبات لظهوره.'})
        except (OSError,ValueError,RuntimeError):
            checks.append({'name':'device_index_temp','status':'not_verified','reason':'الفهرس غير متاح أو يحتاج إعدادًا.'})
    return {'checks':checks,'passed':sum(x['status']=='pass' for x in checks),
            'not_verified':[x['name'] for x in checks if x['status']!='pass'],
            'note':'لا توجد أوامر ماوس/لوحة مفاتيح أو استدعاءات Gemini ضمن هذا الاختبار.'}
