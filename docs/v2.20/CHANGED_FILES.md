# تغييرات v2.20.0 مقارنة بـv2.19.0

| الملف | الحالة | الغرض |
|---|---|---|
| `.github/workflows/windows-build.yml` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `BUILD_BARQ.bat` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `BUILD_WINDOWS_EXE.bat` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `README.md` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `SOURCE_MANIFEST_SHA256.json` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `START_HERE_AR.txt` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `WINDOWS_BUILD_GUIDE_AR.md` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `agent/orchestrator.py` | modified | نتيجة سريعة للأداة والحفظ، استكمال منفصل، قراءة السياق الأولي وخريطة مركزة. |
| `api.py` | modified | خيار defer_replan المتوافق مع العملاء الأقدم. |
| `brain/coordinator.py` | modified | حفظ التخطيط التالي واستعادته وإلغاؤه مع الاحتفاظ بالنتائج المنفذة. |
| `core/version.py` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `docs/v2.20/BUILD_REPORT_AR.md` | added | تقرير الإصدار أو سجل التحقق. |
| `docs/v2.20/CHANGED_FILES.json` | added | تقرير الإصدار أو سجل التحقق. |
| `docs/v2.20/CHANGED_FILES.md` | added | تقرير الإصدار أو سجل التحقق. |
| `frontend/package-lock.json` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `frontend/package.json` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `frontend/src/App.tsx` | modified | تركيب نافذة الموافقة خارج سجل الرسائل ومساحة العمل. |
| `frontend/src/components/chat/ApprovalDialog.tsx` | added | نافذة مراجعة عامة تلقائية للخطوة والحفظ، ترتبط بمعرف الموافقة المعروض. |
| `frontend/src/components/chat/BrainStatus.tsx` | modified | مراحل دقيقة ووقت انتظار فعلي وإزالة الحالة القديمة بعد تجهيز الموافقة. |
| `frontend/src/components/chat/Message.tsx` | modified | بطاقات مختصرة وزر مراجعة للنافذة ومسار إجراءات موحد. |
| `frontend/src/components/layout/SettingsModal.tsx` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `frontend/src/components/workspace/WorkspaceStudio.tsx` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `frontend/src/lib/agentOutcome.ts` | modified | تمييز نتيجة أداة مكتملة مع خطة تالية مؤجلة. |
| `frontend/src/lib/approvals.ts` | added | اختيار أحدث موافقة وأسماء العمليات المفهومة. |
| `frontend/src/lib/chat.ts` | modified | الأوامر النصية للموافقة تستخدم نفس مسار التنفيذ المحمي. |
| `frontend/src/lib/taskActions.ts` | added | تنفيذ موحد للموافقة والحفظ والاستكمال، حماية الضغط المكرر، وإظهار النتيجة قبل النموذج. |
| `frontend/src/store/index.ts` | modified | حالة انشغال المهمة ومراحل مؤقتة لا تعيد دورانًا لا نهائيًا عند التحميل. |
| `frontend/tests/approval-flow.ts` | added | سلوك الموافقة والاستهلاك الفوري للمعرف والاستكمال ومنع تكرار الكتابة. |
| `router/engine.py` | modified | مهلة للنموذج وميزانية إجمالية للتخطيط السحابي مع بديل مسموح. |
| `scripts/build_windows.ps1` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `scripts/installer.iss` | modified | الإصدار أو دليل البناء أو بوابات التحقق والبصمات. |
| `scripts/ui_approval_smoke.py` | added | فحص متصفح فعلي مع أداة وحفظ حقيقيين في مشروع مؤقت ونموذج موقوف عمدًا. |
| `scripts/ui_command_smoke.py` | modified | مراعاة النافذة الجديدة في فحص الأوامر السابق. |
| `scripts/verify_source_integrity.py` | modified | اشتراط ملفات الموافقة واختبارها ضمن السورس. |
| `tests/test_barq_coordinated_agent.py` | modified | تحديث فحص توزيع المكونات إلى خدمة الإجراءات ونافذة الموافقة. |
| `tests/test_v220_fast_approvals.py` | added | 5 اختبارات للاستجابة قبل النموذج، الاستعادة، الواجهة، والمهل. |
| `verification/v2.20/browser-approvals.json` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/browser-approvals.log` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/browser-commands.json` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/browser-commands.log` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/frontend-validation.log` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/python-tests.log` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/python-tests.xml` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/source-preflight.log` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/source-self-test.json` | added | تقرير الإصدار أو سجل التحقق. |
| `verification/v2.20/targeted-tests.log` | added | تقرير الإصدار أو سجل التحقق. |
| `web/react/assets/index-D-6OzpxL.js` | added | أصول React المعاد بناؤها. |
| `web/react/assets/index-DErvsRMr.css` | removed | أصول React المعاد بناؤها. |
| `web/react/assets/index-EUfUlAFm.js` | removed | أصول React المعاد بناؤها. |
| `web/react/assets/index-aIN40n1e.css` | added | أصول React المعاد بناؤها. |
| `web/react/index.html` | modified | أصول React المعاد بناؤها. |
