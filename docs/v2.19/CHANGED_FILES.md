# تغييرات v2.19.0 مقارنة بـv2.18.3

| الملف | الحالة | الغرض |
|---|---|---|
| `.github/workflows/windows-build.yml` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `BUILD_BARQ.bat` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `BUILD_WINDOWS_EXE.bat` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `README.md` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `SOURCE_MANIFEST_SHA256.json` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `START_HERE_AR.txt` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `WINDOWS_BUILD_GUIDE_AR.md` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `agent/task_intent.py` | modified | فصل الطلب الأساسي عن الشروط، وفهم الإنشاء والأسئلة والنفي دون إسقاط المواصفات. |
| `api.py` | modified | مدخل موحد واستكمال للطلبات، وربط التخطيط بمعرف الأمر وحماية المعدل والمحادثة. |
| `brain/commands.py` | added | حفظ استقبال الأوامر وسياقها وخصوصيتها في SQLite، والاستعادة والإلغاء. |
| `brain/coordinator.py` | modified | تنسيق الاستقبال والفهم والحفظ والتخطيط، وعدم حجب الأوامر الواضحة بتعطل نموذج. |
| `brain/failures.py` | added | تشخيص آمن ومحدد دون كشف جسم رد المزود أو المفاتيح. |
| `brain/understanding.py` | modified | إرجاع سبب التعطل وتطبيع الحقول المساعدة مع التحقق من العقد. |
| `command_network/contracts.py` | modified | تمييز تنسيق JSON النصي من اشتراط API أصلي. |
| `command_network/control.py` | modified | فحص إتاحة للقراءة فقط وتحرير محاولة التعافي عند إلغاء الاتصال. |
| `command_network/routing.py` | modified | عدم حجز التعافي في المعاينة وتطبيق شرط JSON الأصلي عند طلبه فقط. |
| `command_network/service.py` | modified | توجيه عقود الفهم والتخطيط حسب غرضها النصي، لا الكلمات داخل البيانات. |
| `core/version.py` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `docs/v2.19/BUILD_REPORT_AR.md` | added | تقرير أو سجل تحقق الإصدار. |
| `docs/v2.19/CHANGED_FILES.json` | added | تقرير أو سجل تحقق الإصدار. |
| `docs/v2.19/CHANGED_FILES.md` | added | تقرير أو سجل تحقق الإصدار. |
| `docs/v2.19/COMMANDS_USER_GUIDE_AR.md` | added | تقرير أو سجل تحقق الإصدار. |
| `frontend/package-lock.json` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `frontend/package.json` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `frontend/src/App.tsx` | modified | فتح إدارة النماذج من بطاقة الطلب. |
| `frontend/src/components/chat/Message.tsx` | modified | بطاقة سبب التوقف واستكمال نفس الطلب وإدارة النماذج. |
| `frontend/src/components/layout/SettingsModal.tsx` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `frontend/src/components/workspace/WorkspaceStudio.tsx` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `frontend/src/lib/chat.ts` | modified | مدخل الأوامر الموحد والاستكمال المرتبط بالطلب، مع دعم الخادم الأقدم. |
| `frontend/src/store/index.ts` | modified | حفظ بطاقة الطلب ومعرف الأمر ضمن المحادثة. |
| `frontend/tests/chat-coordination.ts` | modified | اختبار حفظ الطلب والاستكمال دون تنفيذ ضمني أو استبداله بدردشة. |
| `monitor/health.py` | modified | تصفير الانتظار القديم عند نجاح النموذج. |
| `router/engine.py` | modified | التحقق بالعقد المناسب، وتشخيص الاستبعاد، وتعافي الاتصال والوضع المحلي. |
| `scripts/build_windows.ps1` | modified | تحديث الإصدار وإدراج وحدات brain صراحة في التغليف. |
| `scripts/installer.iss` | modified | تحديث الإصدار أو دليل البناء أو بصمات الحزمة. |
| `scripts/ui_command_smoke.py` | added | فحص React وFastAPI وEngine وHTTP في متصفح مع سيناريو عطل وإعادة تشغيل واستكمال. |
| `scripts/verify_source_integrity.py` | modified | اشتراط وجود وحدات الأوامر والتشخيص والفهم الجديدة. |
| `tests/test_v219_command_intake.py` | added | 33 حالة لسلوك الاستقبال والتوجيه ومحولات HTTP والتعافي والملكية والنفي. |
| `verification/v2.19/browser-command-smoke.json` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/browser-command-smoke.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/chat-tests.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/command-intake.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/frontend-validation.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/intake-routing-tests.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/python-tests.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/python-tests.xml` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/recovery-checks.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/reproduced-intake.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/source-preflight.log` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/source-self-test.json` | added | تقرير أو سجل تحقق الإصدار. |
| `verification/v2.19/targeted-core.log` | added | تقرير أو سجل تحقق الإصدار. |
| `web/react/assets/index-BXc5iWww.js` | removed | أصول React المبنية من السورس الجديد. |
| `web/react/assets/index-CYTIIBig.css` | removed | أصول React المبنية من السورس الجديد. |
| `web/react/assets/index-DErvsRMr.css` | added | أصول React المبنية من السورس الجديد. |
| `web/react/assets/index-EUfUlAFm.js` | added | أصول React المبنية من السورس الجديد. |
| `web/react/index.html` | modified | أصول React المبنية من السورس الجديد. |
