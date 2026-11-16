# إصلاح خطأ FastAPI أثناء بناء BARQ v2.30

## السبب

السورس السابق يستدعي `app.add_event_handler('startup', ...)` في `api.py`.
هذه الواجهة قد تغيب في بعض نسخ FastAPI/Starlette الحديثة، فتفشل
عملية استيراد `api.py` أثناء جمع اختبارات pytest كلها، ويظهر
`AttributeError: 'FastAPI' object has no attribute 'add_event_handler'`.

يستبدل الإصلاح ذلك بمُعالج بدء تشغيل `lifespan` مع استمرار
وظيفة إعادة تشغيل فهرسة الملفات بعد موافقة المستخدم.

## التطبيق

1. فك هذا الباتش في جذر مشروع BARQ (حيث يوجد `api.py`)، أو بجوار مجلد `BARQ`.
2. شغّل `APPLY_BARQ_FASTAPI_STARTUP_FIX.bat`.
3. سيُنشأ ملف احتياطي `api.py.before-fastapi-startup-fix.bak` في أول تطبيق.
4. أعد تشغيل أداة البناء الرسمية من مجلد السورس الأصلي.

## التحقق

من مجلد BARQ وبعد تثبيت الاعتمادات:

    py -3.11 -m pytest --collect-only -q
    py -3.11 -m pytest tests/test_project_state.py tests/test_react_backend_integration.py -q

أرسل `release/python-tests.log` كاملًا إذا ظهرت أخطاء أخرى؛
لا تتجاوز بوابة الاختبارات ولا تشغّل Inno Setup بصورة منفصلة.

## حدود التحقق

تم التحقق في Linux من جمع 1349 اختبارًا، ونجاح 44 اختبارًا مستهدفًا،
وفحص السورس واتساق الإصدار. لم يُتحقق من نجاح بناء EXE على Windows.
الرسالة في لقطة الشاشة مقطوعة، لذا يُرجى مقارنة اسم الخاصية بالكامل
إذا استمر نفس الخطأ بعد تطبيق الباتش.
