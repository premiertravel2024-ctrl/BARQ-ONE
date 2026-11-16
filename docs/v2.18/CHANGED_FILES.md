# كل الملفات المعدلة مقارنة بالسورس المرفق v2.17

تشمل القائمة ملفات المصدر والاختبارات والتوثيق والسجلات والأصول المبنية. قائمة المصدر القابلة للتشغيل كاملة في الأرشيف؛ لا توجد ملفات node_modules أو بيانات مستخدم محلية.

| الملف | الحالة | السبب |
|---|---|---|
| `.env.example` | عُدّل | توثيق المهلات والمحاولات وميزانية المهمة وسياق Ollama التكيفي. |
| `.github/workflows/windows-build.yml` | عُدّل | إصدار 2.18 ورفع سجلات الفشل وفحص المثبت وبصمات Setup وPortable. |
| `BUILD_BARQ.bat` | عُدّل | تحديث بيانات الإصدار 2.18.0 واتساق الواجهة ومدخلات البناء دون تغيير الاعتماديات المقفلة. |
| `BUILD_WINDOWS_EXE.bat` | عُدّل | تحديث بيانات الإصدار 2.18.0 واتساق الواجهة ومدخلات البناء دون تغيير الاعتماديات المقفلة. |
| `README.md` | عُدّل | إبراز تقرير v2.18 وحدود اعتماد Windows قبل الملاحظات التاريخية. |
| `agent/orchestrator.py` | عُدّل | Schema صارم، استكمال فحص متوقف، أدوات البناء واختبارات مجلد فرعي وميزانية جولات محدودة. |
| `agent/task_intent.py` | عُدّل | فهم متابعة المشروع والخطأ والتمييز بين بناء مشروع قائم وإنشاء مشروع جديد. |
| `api.py` | عُدّل | تقييد العميل والأصل وIPv6 وWebSocket وحدود التخطيط، وإعادة استخدام جرد النماذج. |
| `api_routes/models.py` | أضيف | مصدر مركزي لحالة النماذج وأسباب عدم الجاهزية. |
| `brain/coordinator.py` | عُدّل | استعادة checkpoints وملكية المحادثة وحالة الإنجاز واستكمال الحفظ دون إعادة العملية. |
| `brain/state.py` | عُدّل | تحديث ذري للأحداث والأدلة، وحفظ سجل الفحوص المنفذة بعد الحفظ. |
| `brain/understanding.py` | عُدّل | محلل JSON المركزي وفهم المتابعات من المهمة النشطة. |
| `build/jobs.py` | عُدّل | ربط البناء بالشات، رفض مخرجات قديمة، وقراءة سجل العملية بذاكرة محدودة. |
| `core/adaptive_resources.py` | عُدّل | تحديد سياق Ollama من موارد الجهاز ونمط الأداء وحد النموذج. |
| `core/json_contracts.py` | أضيف | استخراج JSON واحد مع رفض الحقول المكررة والوثائق المتعددة. |
| `core/version.py` | أضيف | مصدر إصدار التشغيل الموحد 2.18.0. |
| `desktop.py` | عُدّل | --version واختبار HTTP والتخطيط والإغلاق وحماية بيانات المستخدم أثناء self-test. |
| `docs/v2.18/BUILD_REPORT_AR.md` | أضيف | توثيق الإصلاحات والقبول والملفات المعدلة وتعليمات البناء وحدود التحقق. |
| `docs/v2.18/CHANGED_FILES.json` | أضيف | توثيق الإصلاحات والقبول والملفات المعدلة وتعليمات البناء وحدود التحقق. |
| `docs/v2.18/CHANGED_FILES.md` | أضيف | توثيق الإصلاحات والقبول والملفات المعدلة وتعليمات البناء وحدود التحقق. |
| `docs/v2.18/INSTALL_AR.md` | أضيف | توثيق الإصلاحات والقبول والملفات المعدلة وتعليمات البناء وحدود التحقق. |
| `frontend/package-lock.json` | عُدّل | تحديث بيانات الإصدار 2.18.0 واتساق الواجهة ومدخلات البناء دون تغيير الاعتماديات المقفلة. |
| `frontend/package.json` | عُدّل | تحديث بيانات الإصدار 2.18.0 واتساق الواجهة ومدخلات البناء دون تغيير الاعتماديات المقفلة. |
| `frontend/src/components/chat/Message.tsx` | عُدّل | توحيد حالة التنفيذ وإعادة التخطيط وحفظ إيصال الملف عند انقطاع الاستكمال. |
| `frontend/src/components/chat/ModelSelector.tsx` | عُدّل | عرض سبب عدم جاهزية النموذج الذي يعيده الخادم. |
| `frontend/src/components/layout/SettingsModal.tsx` | عُدّل | تحديث بيانات الإصدار 2.18.0 واتساق الواجهة ومدخلات البناء دون تغيير الاعتماديات المقفلة. |
| `frontend/src/components/workspace/WorkspaceStudio.tsx` | عُدّل | تحديث بيانات الإصدار 2.18.0 واتساق الواجهة ومدخلات البناء دون تغيير الاعتماديات المقفلة. |
| `frontend/src/lib/agentOutcome.ts` | أضيف | تحويل موحد ومستقل عن DOM لحالات المهمة. |
| `frontend/src/lib/backend.ts` | عُدّل | نقل سبب عدم جاهزية النموذج إلى الواجهة. |
| `frontend/src/lib/chat.ts` | عُدّل | استكمال paused وإيصالات الحفظ وفصل التنقل عن نجاح العمليات. |
| `frontend/src/lib/uiEvents.ts` | أضيف | إشعارات واجهة آمنة في Node وفي حال تعطل مستمع التنقل. |
| `frontend/src/store/index.ts` | عُدّل | حالة إيصال الحفظ وتعطل التخطيط ومصدر الهوية الافتراضي في الخادم. |
| `frontend/tests/chat-coordination.ts` | عُدّل | تغطية سلوكية للأعطال والاستكمال وعدم إعادة الحفظ والتشغيل. |
| `main.py` | عُدّل | الإصدار المركزي وتمرير ردود CLI عبر Brain وشخصية برق. |
| `providers/client.py` | عُدّل | المهلات الموحدة وطلبات Ollama الأصلية بسياق فعلي. |
| `providers/reliability.py` | أضيف | إعدادات محدودة للمهلات وexponential backoff مع jitter. |
| `providers/streaming.py` | عُدّل | نفس مهلات وسياق Ollama للطلب المتدفق. |
| `pytest.ini` | أضيف | تثبيت نطاق asyncio للاختبارات ومنع اختلاف الافتراضات بين الإصدارات. |
| `requirements-test.txt` | أضيف | اعتماديات الاختبار دون فرض أدوات التغليف المكتبي. |
| `router/config.py` | عُدّل | رفض أولوية مزود خارج 0–100 أثناء التحميل. |
| `router/context.py` | عُدّل | مواءمة حجم السياق المختار مع حد Ollama والنموذج. |
| `router/engine.py` | عُدّل | محاولات مؤقتة محدودة، فحص الحصص في كل محاولة، وحد سجل القياسات. |
| `scripts/build_short_path.py` | عُدّل | نسخ سجلات الفشل، وعدم إعادة إنشاء ZIP جرى التحقق منه، وفصل مخرجات recovery. |
| `scripts/build_windows.ps1` | عُدّل | بوابات بناء مرتبة، سجلات XML، فحص المثبت، Portable وبصمات المخرجات. |
| `scripts/chat_coordination_smoke.mjs` | عُدّل | اختبار fixture بديل لإثبات تمرير فشل عملية Node الفرعية. |
| `scripts/installer.iss` | عُدّل | إصدار جديد ومعرف smoke منفصل مع الحفاظ على معرف التثبيت العادي وعدم تغيير اختصاراته في الاختبار. |
| `scripts/release_evidence.py` | أضيف | مطابقة مخرجات Windows واختبارات الملف المجمد والمثبت وSHA256. |
| `scripts/smoke_install.ps1` | عُدّل | اختبار تثبيت الملف الناتج وتشغيله وإزالته في مسار مؤقت معزول. |
| `scripts/ui_brain_smoke.py` | عُدّل | تحديث محددات مساحة العمل ومسار الشات الحقيقي والعودة من الهاتف دون شات ثانٍ. |
| `scripts/verify_release_consistency.py` | عُدّل | إضافة فحص تطابق إصدار التشغيل المركزي مع بقية مدخلات البناء. |
| `scripts/verify_source_integrity.py` | عُدّل | إضافة ملفات العقود والاستعادة والتغليف الجديدة إلى فحص الاكتمال. |
| `tests/test_adaptive_ui_v216.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_barq_brand.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_chat_smoke_launcher_regression.py` | عُدّل | استبدال فحص العبارات بتشغيل سلوكي حقيقي واختبار فشل الطفل. |
| `tests/test_frontend_build_gate_v2142.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_guardian_v214.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_provider_recovery_v217.py` | عُدّل | إثبات حالات frontend المشتركة بالتنفيذ بدل مطابقة نص implementation. |
| `tests/test_unified_main_chat_execution.py` | عُدّل | إثبات إشعارات التنقل وتنسيق الشات بالتنفيذ مع إبقاء عقد الواجهة. |
| `tests/test_v217_stability.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_v218_execution.py` | أضيف | إنشاء ملفات وتعديلها وحفظها وتشغيل pytest فعليًا واختبار حجب البناء دون Windows. |
| `tests/test_v218_recovery.py` | أضيف | إعادة إنتاج وإثبات إصلاح توقف النماذج والاستعادة والملكية والعقود والتزامن. |
| `tests/test_v218_resources_and_security.py` | أضيف | موارد ضعيفة ومهلات وbackoff وحصص وOllama وأصل HTTP/WebSocket. |
| `tests/test_v282_installer_repair.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_v283_flat_launcher.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_v285_ts_build_fix.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tests/test_windows_package.py` | عُدّل | تتبع الإصدار المركزي الحالي مع الحفاظ على فحوص السلوك وهوية التثبيت؛ لا يُثبت رقم الإصدار القديم. |
| `tools/registry.py` | عُدّل | التعرف على مشروع يحتوي test_*.py في جذره لتشغيل الاختبار الموافق عليه. |
| `verification/v2.18/final-chat.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/final-frontend.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/final-imports.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/final-python311.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/final-python311.xml` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/final-react-build.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/final-typescript.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/frontend-packages.txt` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/baseline-build.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/baseline-chat.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/baseline-frontend.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/baseline-icons.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/baseline-npm-ci.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/baseline-python.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/baseline-typecheck.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/browser-install.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/browser-runtime.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/interim-build.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/interim-python.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/interim311-python.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/pip-install.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/pip-test-install.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/pip311-install.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/postfix311-python.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/python311-install.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/react-build-result.json` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/recovery-after.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/smoke-deps.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/source-self-test.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/targeted-last.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/ui-browser-latest-error.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/ui-browser-smoke.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/history/v218-critical.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/pristine311-python.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/python311-packages.txt` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/reproduced-v218.log` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/source-self-test.json` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/ui-browser-result.json` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `verification/v2.18/verification-result.json` | أضيف | دليل تنفيذ أو سجل محاولة محفوظ للمراجعة؛ ليس سجل بناء Windows. |
| `web/react/assets/index-BhyceSyC.css` | استبدل أثناء بناء الأصول | إعادة بناء React من السورس الحالي واستبدال أسماء الأصول المشتقة من محتواها. |
| `web/react/assets/index-CYTIIBig.css` | أضيف | إعادة بناء React من السورس الحالي واستبدال أسماء الأصول المشتقة من محتواها. |
| `web/react/assets/index-DRF2O9K4.js` | استبدل أثناء بناء الأصول | إعادة بناء React من السورس الحالي واستبدال أسماء الأصول المشتقة من محتواها. |
| `web/react/assets/index-DmkoxnzZ.js` | أضيف | إعادة بناء React من السورس الحالي واستبدال أسماء الأصول المشتقة من محتواها. |
| `web/react/index.html` | عُدّل | إعادة بناء React من السورس الحالي واستبدال أسماء الأصول المشتقة من محتواها. |
