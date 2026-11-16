# BARQ AI v2.8.5 — تصحيح بناء واجهة React / TypeScript

## تشخيص الخطأ
التثبيت توقف في Type-checking and building React UI (exit 2)،
قبل بدء PyInstaller أو Inno Setup. من السورس:
- `NetworkMap.tsx` كان يستورد `RefreshCw` دون استخدام مع تفعيل `noUnusedLocals`.
- `WorkspaceStudio.tsx` كان يستخدم `Folder` في Activity Bar دون استيراده من `lucide-react`.

## الإصلاحات
- إزالة الاستيراد غير المستخدم وإضافة الاستيراد الناقص.
- تحديث بيانات الإصدار إلى 2.8.5 في ملفات البناء والمثبت والاختبارات.
- الإبقاء على `npm run build` (TypeScript + Vite) مرحلة إلزامية قبل إنتاج أي EXE.
- توسيع CI ليشمل main وpull requests مع الحفاظ على فحص EXE والمثبت.

## التثبيت
1. فك ZIP بالكامل في مجلد جديد، وادخل مجلد `BARQ`.
2. شغّل `BUILD_BARQ.bat` (لا تشغّل `installer.iss` مباشرة).
3. عند نجاح كل المراحل سيظهر `release/BARQ_Setup_2.8.5.exe`.

## حدود التحقق
أُجريت اختبارات Python الكاملة وفحوصات تحليل TypeScript النصي.
لم تتوفر حزم npm عبر الإنترنت في بيئة إعداد هذا التحديث، لذا لم ينجح إجراء
TypeScript/Vite build الفعلي هنا أو بناء Windows EXE. فحصهما لا يزال إلزاميًا على Windows.
لا تعتبر وجود الملف المصدر دليلاً على نجاح التثبيت قبل أن ينتهي BUILD_BARQ.bat بنجاح.
