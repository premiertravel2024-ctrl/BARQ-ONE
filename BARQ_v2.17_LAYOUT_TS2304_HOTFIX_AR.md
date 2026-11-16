# إصلاح بناء BARQ AI v2.17 — TS2304 (Layout)

هذا تحديث تصحيحي لنفس إصدار v2.17.0، وليس إصدار ميزات جديدًا.

## الخطأ
كان `WorkspaceStudio.tsx` يستخدم النوع `Partial<Layout>` بدون استيراد `Layout`، ففشل `tsc --noEmit` عند بناء React على Windows.

## ما تغير
- `frontend/src/components/workspace/WorkspaceStudio.tsx`: استيراد `type Layout` من `./studioHooks`.
- `scripts/verify_source_integrity.py`: فحص مبكر لاكتشاف استخدام Layout من دون استيراد معرّف.
- `tests/test_release_integrity_v2161.py`: ثلاثة اختبارات مضافة تثبت اكتشاف الخطأ ونجاح الاستيراد الصحيح.
- `CHECK_BARQ_UI.bat`: تصحيح تسمية الإصدار في نافذة فحص React.

## التحقق المنجز
- فحص سلامة ملفات السورس: ناجح.
- 686 اختبار Python ناجح، و65 اختبارًا فرعيًا ناجحًا.
- 8 اختبارات Node للواجهة نجحت.
- فحص TypeScript المحدود دون حزم npm: لا توجد أخطاء TS2304 بالأسماء غير المعرفة.

## ما لم يتم التحقق منه
لا يمكن إثبات نجاح `npm run build` الكامل أو Windows EXE هنا بسبب عدم توفر تنزيل حزم npm من registry.npmjs.org. الاختبار المحدود لا يعادل بناء React الحقيقي. واختبار chat coordination الإضافي يتطلب esbuild.

## طريقة استخدام السورس الكامل على Windows
1. فك ZIP في مجلد جديد وفارغ.
2. افتح مجلد `BARQ` وشغّل `CHECK_BARQ_UI.bat` (يتطلب Python 3.11 وNode.js/npm).
3. إذا نجح فحص React بالكامل، شغّل `BUILD_BARQ.bat` لبناء المثبت.
4. لا تشغّل `scripts/installer.iss` منفصلًا قبل نجاح بناء EXE.

## طريقة استخدام الإصلاح الصغير
فك ZIP داخل المجلد الذي يحتوي على مجلد `BARQ` الموجود، واسمح باستبدال الملفات الأربعة. لا تضع ملفات ZIP داخل `frontend` مباشرة.
