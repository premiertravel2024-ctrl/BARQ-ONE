# الملفات المتغيرة من v2.18.1 إلى v2.18.2

| الملف | الحالة | السبب |
|---|---|---|
| `.github/workflows/windows-build.yml` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `BUILD_BARQ.bat` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `BUILD_WINDOWS_EXE.bat` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `README.md` | modified | التقرير وقائمة الملفات وتعليمات إعادة البناء وحدود التحقق. |
| `cache/store.py` | modified | اتصال ملفي محدود بعمر العملية مع قفل للتزامن والحفاظ على دعم الكاش في الذاكرة. |
| `coding/project_state.py` | modified | إغلاق الاتصال إذا تعذر إنشاء مخطط قاعدة بيانات المشروع. |
| `core/sqlite.py` | modified | إنهاء المعاملة وإغلاق الاتصال deterministically في النجاح والفشل؛ إغلاق الاتصال عند فشل PRAGMA. |
| `core/version.py` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `desktop.py` | modified | ترتيب إغلاق السيرفر والتنظيف، ودليل cleanup_completed وتشخيص مرحلة الخطأ دون إخفائه. |
| `docs/v2.18.2/BUILD_REPORT_AR.md` | added | التقرير وقائمة الملفات وتعليمات إعادة البناء وحدود التحقق. |
| `docs/v2.18.2/CHANGED_FILES.json` | added | التقرير وقائمة الملفات وتعليمات إعادة البناء وحدود التحقق. |
| `docs/v2.18.2/CHANGED_FILES.md` | added | التقرير وقائمة الملفات وتعليمات إعادة البناء وحدود التحقق. |
| `frontend/package-lock.json` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `frontend/package.json` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `frontend/src/components/layout/SettingsModal.tsx` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `frontend/src/components/workspace/WorkspaceStudio.tsx` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `scripts/build_windows.ps1` | modified | الإصدار 2.18.2 واشتراط cleanup_completed في اختبار EXE المجمد. |
| `scripts/installer.iss` | modified | تحديث إصدار التشغيل أو بيانات البناء والواجهة إلى 2.18.2. |
| `scripts/release_evidence.py` | modified | رفض اعتماد مخرجات إصدار لا تؤكد نجاح تنظيف self-test. |
| `scripts/smoke_install.ps1` | modified | اشتراط نجاح التنظيف في تقرير التطبيق المثبت. |
| `scripts/verify_source_integrity.py` | modified | التأكد من وجود وحدتي SQLite والكاش المطلوبتين للبناء. |
| `tests/test_v2182_sqlite_lifecycle.py` | added | 15 حالة سلوكية لدورة حياة SQLite وقفل Windows والبيانات والتزامن وفشل التنظيف. |
| `verification/v2.18.2/frontend-validation.log` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/high-memory.log` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/high-memory.xml` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/low-memory.log` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/low-memory.xml` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/normal.log` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/normal.xml` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/reproduced-sqlite-lock.log` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/source-self-test.json` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/sqlite-lifecycle.log` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `verification/v2.18.2/test-runs.json` | added | سجل إعادة الإنتاج أو التحقق الفعلي من النسخة الجديدة. |
| `web/react/assets/index-BRjimcLo.js` | added | أصول React المبنية من سورس v2.18.2. |
| `web/react/assets/index-Lf2OkClE.js` | removed | أصول React المبنية من سورس v2.18.2. |
| `web/react/index.html` | modified | أصول React المبنية من سورس v2.18.2. |
