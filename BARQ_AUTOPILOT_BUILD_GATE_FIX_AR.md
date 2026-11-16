# BARQ v2.30 — Autopilot permission build gate fix

## السبب المثبت

اختبار `scripts/test_autopilot_guard.cjs` رفض موافقة تلقائية على `code_replace`، بينما `frontend/src/lib/approvals.ts` كان يسمح بها للملفات المتتبعة داخل المهمة. ده تضارب حقيقي في سياسة الأمان وليس خطأ Node.js ولا esbuild.

## التعديلات

- `frontend/src/lib/approvals.ts`: منع الموافقة التلقائية على `code_replace` والإبقاء على أتمتة القراءة والتخطيط وتجهيز ملفات المهمة المصرّح بها.
- `scripts/build_windows.ps1`: تقديم اختبار الصلاحيات ليعمل فور تثبيت الحزم والتحقق من esbuild، قبل فحص TypeScript وباقي الواجهة.
- `tests/test_windows_package.py`: اختبار انحدار يحمي ترتيب بوابات البناء ويرفض إعادة السماح التلقائي لـ code_replace.

## اختبارات نُفذت

- إعادة إنتاج فشل الاختبار نفسه في السورس الأصلي.
- نجاح `node scripts/test_autopilot_guard.cjs` بعد التعديل.
- نجاح 84 اختبار Python مستهدفًا متعلقًا بالبناء والأمان وFastAPI والتحكم.
- نجاح فحوص سلامة السورس ومطابقة الإصدار واعتمادات CI.
- فحص الصياغة النحوية لـ71 ملف TypeScript دون تشخيصات.

## حدود التحقق

لم يكتمل `npm ci` في بيئة الاختبار (نقص الحزم/الاتصال)، لذا لم يتم تشغيل TypeScript semantic check أو Vite build كاملًا هنا. لم يتم تشغيل PyInstaller وInno Setup على Windows. لا يوجد ضمان بانعدام جميع أخطاء بناء EXE حتى ينجح البناء على جهاز Windows أو CI Windows.

## التشغيل

للسورس الكامل: فك ZIP جديدًا وشغّل `BUILD_BARQ.bat`. لا تجمع بين نسختين مختلفتين.

للباتش: فك ZIP **داخل جذر BARQ** بجانب `BUILD_BARQ.bat`، شغّل `APPLY_BARQ_AUTOPILOT_GUARD_FIX.bat`. السكربت يقارن بصمات SHA256 ويرفض تعديل أي ملف من إصدار مختلف؛ ويحفظ النسخة السابقة قبل التعديل.
