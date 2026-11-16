# BARQ AI v2.31.1 — إصلاح بوابة اختبارات البناء الثلاثة على Windows

## سبب المشكلة
في سجل Windows: 1476 اختبارًا ناجحًا، وثلاثة إخفاقات في
`ReactFrontendContract.test_windows_pipeline_builds_react_first` و
`test_npm_retains_lock_and_integrity_and_fallback` و
`test_python_is_installed_once_in_isolated_venv_with_shared_cache`.

- اختبار ترتيب البناء استخدم `script.index('PyInstaller')` فالتقط تعليقًا مبكرًا في سكربت PowerShell بدل خطوة التغليف الحقيقية. الترتيب الحقيقي لمراحل React وPython والتغليف سليم.
- اختبار npm افترض أن مسار `npm_config_cache` ينتهي بسلسلة نصية فيها `/` فقط؛ بينما Windows يستخدم `\`.
- اختبار pip كرر نفس افتراض الفاصل النصي الخطأ.

## التغييرات المقصودة على الاختبارات القائمة
1. `tests/test_react_frontend_contract.py`: تحقق من استدعاء مرحلتَي بناء React والتغليف الحقيقتين داخل PowerShell، ومن ترتيبهما.
2. `tests/test_v231_dependency_download_manager.py`: قارن مسارات الكاش باستخدام `pathlib.Path` على النظام الحالي بدل فواصل POSIX النصية.

لا تعديل على محرك التنفيذ، أو واجهة الصوت، أو ترخيص الصلاحيات، أو بوابات الأمان. لا Skip إضافي، ولا إزالة اختبارات. هذا الإصلاح خاص بعقد الاختبار عبر الأنظمة؛ وليس تجاوزًا لشروط بناء EXE.

## التحقق في بيئة التطوير
- قبل التصحيح أُعيد إنتاج فشل اختبار ترتيب React.
- بعد التصحيح: `84 passed, 35 subtests passed` في وحدات البناء والكاش وWindows والتغليف والارتباط الصوتي.
- فحوص `verify_source_integrity.py`، `verify_release_consistency.py`، `verify_ci_dependencies.py`، `audit_release_readiness.py` تُنفَّذ عند تغليف السورس.
- الاختبار الشامل في بيئة Linux تجاوز المهلة وظهرت إخفاقات أخرى غير مشخصة في تلك البيئة؛ لا يمكن اعتباره PASS.
- لم يُنفَّذ بناء EXE أو اختبارات Windows حقيقية على هذه الآلة. النتيجة النهائية للمثبت **NOT VERIFIED** حتى نجاح `BUILD_BARQ.bat` على Windows.

## كيفية التطبيق
استخدم سورس ZIP الكامل في مجلد نظيف ثم `BUILD_BARQ.bat`، أو فك باتش التعديل بجانب مجلد BARQ الحالي وشغّل `APPLY_BARQ_THREE_GATES_FIX.bat` قبل إعادة البناء. الباتش يتحقق من بصمات الملفين قبل أي تعديل ويحتفظ بنسخة احتياطية.
