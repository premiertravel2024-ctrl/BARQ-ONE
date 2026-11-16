# BARQ AI v2.31.0 — Execution Engine (نسخة تطويرية قابلة للاختبار)

## ملخص واضح

النسخة **ليست إصدارًا نهائيًا لتنفيذ السيناريو الصوتي الكامل**؛ هي مرحلة أولى فعلية من تحويل التحكم في الكمبيوتر إلى محرك موحّد. تحافظ على الشات، Google Live، الأدوات، إعدادات الموافقات، المصدر، وواجهة RTL. لا تمنح Administrator ولا تلغي حماية Windows.

## خريطة السورس قبل التعديل (Phase 0)

1. الشات: `api.py` → `computer_control/api.py` → `computer_control/executor/manager.py` → `Tools.act`.
2. المكالمة الصوتية: `voice/live.py` → `voice/computer_tools.py` → `Manager.start` / `Manager.launch_direct`.
3. أدوات التحكم الأصلية: `computer_control/tools/execute.py` + `computer_control/safety/policy.py` + UIA adapters.
4. GitHub: `github/repositories.py` (clone + preview/install approvals مستقلة).
5. برمجة المشاريع: `agent/orchestrator.py`, `tools/registry.py`, `build/jobs.py` (مسارات تنفيذ قائمة).
6. حفظ الحالة: `computer_control/state_store.py` (checkpoint status بدون أدوات/نصوص حساسة).
7. واجهة: `frontend/src/components/workspace/ComputerControl.tsx` + settings UI.

**فجوات مؤكدة:** تنفيذ `run_command` القديم باستخدام shell=True، تعدد المشغلات، غياب إدارة خادم Vite، إسناد صلاحيات المشروع، وغياب E2E على Windows. المزيد من التكامل وإلغاء التكرار ما زال مطلوبًا.

## ما نُفّذ فعلًا

- `execution/runner.py`: تشغيل بنيوي من برنامج معروف + args منفصلة، `shell=False`، منع مدخلات `.cmd` الخطرة، تطهير مفاتيح البيئة، timeout شامل وخمول، حد للناتج والسجل، وإلغاء مجموعة العمليات على Windows باستخدام Job Object.
- `computer_control/tools/execute.py`: مسار `run_command` القديم صار يمر عبر Runner بعد موافقة السياسة؛ لا ينفذ النص في shell. بعض المشغّلات الأخرى الموجودة في GitHub/Build لم تُنقل بعد.
- `execution/services.py`: إدارة خادم تطوير، اختيار منفذ محلي، التحقق بـHTTP 200، إيقاف وتتبع الحالة؛ مملوك لعمر عملية BARQ، وليس خدمة مستقلة بعد الإغلاق.
- `execution/grants.py`: صلاحيات صريحة لكل مجلد/نوع مهمة، منع جذر القرص وجذر حساب المستخدم والمجلدات الحساسة، إلغاء فوري، حل الروابط للمسار الحقيقي، مع إبقاء المجلدات المسموح بها سابقًا.
- `computer_control/safety/policy.py`: الملفات الموجودة داخل grant بحق `write` لا تحتاج موافقة لكل استبدال عادي؛ خارج الـgrant تستمر الموافقة. العمليات المحظورة لا تتحول إلى مسموحة.
- `execution/service.py` و`execution/react_mission.py`: مسار بدء مهمة مشترك للشات والصوت، مع وصفة React مركبة تتعرف على الأمر المصري، وتفحص grant أولًا، ثم تنشئ المشروع وتبنيه وتتحقق من HTTP 200 وتطلب فتح VS Code. إذا لم تُرصد نافذة VS Code، تظهر `needs_review` بدل ادعاء النجاح. بقية المهام تستمر عبر Manager وAudit وبوابة الموافقات على الشاشة.
- `computer_control/state_store.py`: سجل `steps` لكل مهمة ببصمة المعاملات وحالة بدأ/اكتمل؛ يمنع نجاحًا بلا تحقق. **هذا ليس بعد استكمالًا حقيقيًا بعد انقطاع الكهرباء/التطبيق.**
- `execution/known_folders.py`: استخدام Windows Known Folder API الحقيقي (بما في ذلك Desktop المحوّل إلى OneDrive).
- `execution/recipes.py`: إنشاء مشروع React/Vite أولي من قالب محلي بدون npm create أو كتابة فوق مشروع سابق. تثبيت الاعتماديات/البناء وخادم التطوير ببوابة grants، `npm install --ignore-scripts`، وقراءة دليل build الحقيقي.
- `execution/doctor.py`: فحص محلي لوجود Git / Node / Python / VS Code / حزم UIA / LibreHardwareMonitor بدون تنزيل أو صلاحيات إضافية.
- `computer_control/api.py`: واجهات grants، native folder picker، doctor وpreview؛ مداخل الشات والصوت بقيت متوافقة.
- `frontend/.../ComputerControl.tsx`: مدير grants واختيار فولدر وscope/إلغاء وفحص الأدوات داخل إعدادات التحكم.
- `scripts/windows_e2e.py` و`RUN_WINDOWS_E2E.bat`: فحص على Windows الحقيقي مع JSON + Markdown، وفصل FAIL عن NOT_VERIFIED، والتنزيل فقط عند `--network`، وتجربة Desktop فقط عند `--desktop`.
- الإصدار موحّد إلى `2.31.0` في source/frontend/package-lock/Windows build/Inno/CI، وتم تحديث اختبار marker القديم فقط لأن رقم الإصدار تغيّر عمدًا.

## طريقة التفعيل والفحص

1. فك السورس، شغّل `BUILD_BARQ.bat` لبناء التطبيق على Windows 10/11، **وليس** `installer.iss` منفردًا.
2. من Settings → Computer Control فعّل التحكم ثم افتح «صلاحيات المشاريع» واختر فولدرًا مخصصًا. لا تختار قرص النظام كاملًا.
3. اضغط «اسمح للمشروع» بعد تحديد scopes المطلوبة. قراءة/كتابة/إنشاء تتيح العمل على ملفات المشروع؛ Install/Build تحتاج صلاحيات إضافية بنفس المشروع. موافقات HIGH تظل على الشاشة.
4. اضغط «افحص أدوات Windows» لرؤية الأسباب الدقيقة للأدوات الناقصة.
5. شغّل `RUN_WINDOWS_E2E.bat` من مجلد السورس على Windows؛ التقرير داخل `release/BARQ_windows_e2e.md` و`release/BARQ_windows_e2e.json`.
6. للتجربة التي تحتاج npm download نفّذ `RUN_WINDOWS_E2E.bat --network`. لا تفعل ذلك على مشروع غير موثوق. لاختبار إنشاء العينة على سطح المكتب نفسه أضف `--desktop` بعد التأكد من وجود مساحة كافية ومن أنك تريد الملفات هناك.

## حالة مراحل المواصفات الأصلية

| المرحلة | الحالة | ملاحظات |
|---|---|---|
| Phase 0 | منفذ | فحص الخريطة والسورس الأساسي |
| Phase 1 | جزئي | Runner وServiceManager وإدخال chat/voice؛ مشغلات GitHub/Build القديمة لا تزال منفصلة |
| Phase 2 | جزئي | سجل steps وwrite-ahead؛ مطابقة/reconcile واستكمال نفس المهمة بعد إعادة التشغيل غير مكتمل |
| Phase 3 | جزئي | grants + settings + policy؛ بطاقات تثبيت dependencies غير الموثوقة تحتاج ربط واجهة إضافي |
| Phase 4 | جزئي | Doctor قراءة فقط؛ فحوص الإصدارات وحلول الأعطال التفاعلية ناقصة |
| Phase 5 | جزئي | وصفة مركبة دخلت مسار chat/voice، ونُفذت بفوايك؛ لم تُتحقق بعد على Windows الحقيقي/VS Code |
| Phase 6 | غير منفذ | UIA wait/tree وتحقيق end-state المطلوب بعد كل نقرة |
| Phase 7 | جزئي | grants UI؛ task timeline لخادم Vite وربط التنفيذ الصوتي الحي غير مكتمل |
| Phase 8 | جزئي | تحقق مستقل في Manager/recipes؛ تقرير ledger الكامل لم يُربط بمخرجات الصوت |
| Phase 9 | جزئي | Windows E2E launcher مُعد، **لم يُشغّل على Windows هنا** |

## نتائج الاختبارات الصادقة

- **103+ اختبار مستهدف PASS** من بيئة Linux (الصلاحيات، Windows build gates، Voice، OpenJarvis، device search، الواجهة الموجودة، اختبارات Execution Engine الجديدة).
- `verify_source_integrity.py`: PASS.
- `verify_release_consistency.py`: PASS.
- `verify_ci_dependencies.py`: PASS.
- تحليل صياغة TypeScript لـ71 ملفًا: **0 syntax errors**؛ **ليس** فحص `tsc --noEmit` دلاليًا.
- الاختبار الكامل للمشروع **لم يكتمل**: أول فشل سببه عدم تثبيت حزمة `esbuild` هنا؛ محاولة `npm ci --offline` فشلت لأن الحزم غير موجودة في الكاش، وليس بسبب تغيير المشروع. لا يُعد ذلك اختبارًا ناجحًا ولا تقرير سلامة للمثبت.
- Windows EXE / Inno / GPU / Live microphone / real desktop **NOT VERIFIED**. لن ندّعي أن كل شيء يعمل قبل المرور الفعلي.

## اختبارات عزل الخطأ والخصوصية

- تمنع الخروج من grant عبر `..` أو المسارات الحساسة؛ تمنع حذفًا دائمًا، ولا تستخدم جملة النموذج لتفعيل التحكم.
- ترفض `cmd/powershell` العشوائي كمشغل shell بدون التدقيق، وترفض معاملات الميتا-حروف لملفات `.cmd`.
- تنظيف متغيرات البيئة المحتوية على KEY/TOKEN/SECRET ومنع تخزين المعاملات الخام في Step Ledger.
- اختبارات إلغاء العملية وانتهاء المهلة، إنشاء مشروع أولي مع اختبار عدم الكتابة فوق مشروع موجود، ورفض تأكيد الصوت بدل شاشة الموافقة.

## مطلوب قبل وصف النسخة بأنها نهائية

توحيد مشغلات GitHub/Build فعليًا، استكمال ledger + reconciliation، إثبات وصفة React في Google Voice على Windows الحقيقي، الحماية التفاعلية لتثبيت سكربتات المستودعات، واستكمال UIA ثم إجراء Windows E2E شامل للمهمة المستهدفة (صوت/شات → VS Code → Desktop → Vite → npm → localhost HTTP 200). أي جزء فشل أو غير مُختبر يُذكر صراحة.
