# BARQ v2.8.2 — مراجعة وإصلاح منظومة بناء Windows

- أصل المشكلة: Inno Setup يستدعي ملف `dist\BARQ\BARQ.exe` قبل وجوده عند استخدام `installer.iss` مباشرة.
- `BUILD_WINDOWS_EXE.bat`: عرض أخطاء البناء وعدم إغلاق النافذة فورًا، والتحقق من علامة النجاح والمثبت.
- `scripts/installer.iss`: تحقق صريح من BARQ.exe ورسالة خطأ مفيدة، ومسارات نسبية محسوبة من `SourcePath`، وإخراج Setup برقم إصدار متوافق.
- `scripts/build_windows.ps1`: الكشف المبكر عن Inno وPython، التحقق من مخرجات PyInstaller، تشغيل Inno بالمسار المطلق، حذف مثبت الإصدار نفسه عند إعادة البناء قبل التحقق.
- `scripts/smoke_install.ps1`: إصلاح إصدار ملف الـ Setup والمسار الثابت إلى Inno.
- `frontend/package.json` و `package-lock.json` و GitHub Actions والاختبارات: توحيد رقم الإصدار 2.8.2 للمخرجات.
- `BARQ/BUILD_BARQ.bat`: اختصار تشغيل من مجلد ZIP الخارجي لتجنب اختيار `installer.iss` بالخطأ.
- إضافة اختبارات تمنع عودة تعارض المسارات والإصدارات.
- الحفاظ على المعرف `AppId`، ونظام الموافقات، وتكوينات مزودي الموديلات وDeepSeek، وحفظ البيانات.
- هذا تحديث **سورس فقط**. لا يمكن إنشاء أو اختبار EXE الخاص بـWindows من Linux.
