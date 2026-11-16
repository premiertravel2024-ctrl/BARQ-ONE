# BARQ AI v2.31.0 — Windows Python Test Gate Repair

## المشكلة التي أبلغ عنها المستخدم

أوقف بناء Windows الاختباران:

1. `tests/test_execution_react_mission_v231.py::test_composed_react_mission_fake_build_and_real_scaffold`
2. `tests/test_v221_live_editor_hidden_console.py::test_windows_subprocesses_hide_their_consoles`

بقيت بوابة `BUILD_BARQ.bat` و `scripts/build_windows.ps1` كما هي؛ لم يتم تجاوز pytest أو تعطيل اختبار أمان.

## التغييرات

- `execution/react_mission.py`: عزل مراقبة نافذة VS Code في دالة قابلة للاستبدال خلال اختبارات الوحدة، بمهلة قراءة قصوى واستمرار بقية المهمة عند عدم القدرة على تأكيد ظهور النافذة. لا يُعلَن نجاح VS Code إن لم يثبت ظهوره.
- `tests/test_execution_react_mission_v231.py`: اختبار الـWindows الوهمي يحقن مراقب نوافذ وهميًا بدل فحص سطح المكتب الحقيقي أثناء pytest؛ أُضيف اختبار لتأخّر UIA وتأكيد `needs_review` بدل نجاح وهمي.
- `computer_control/tools/execute.py`: توثيق تفويض تنفيذ الأمر إلى Runner المركزي (لا يوجد subprocess مباشر في هذا الغلاف).
- `tests/test_v221_live_editor_hidden_console.py`: تحديث فحص إخفاء الـConsole ليفحص كود Runner المنقول له التنفيذ، وإضافة اختبارات سلوكية لـ `Runner.run` و `Tools.act` على Popen محاكى، تتحقق من `shell=False` و `CREATE_NO_WINDOW`.

## التحقق في هذه البيئة

- اختبار ملفي الانحدار: 9 ناجحة وواحد متخطٍ لاعتماده على TypeScript غير المثبت.
- اختبارات التنفيذ والصلاحيات والصوت وWindows والبناء المستهدفة: 108 ناجحة وواحد متخطٍ لنفس السبب.
- فحص البايثون وصحة المصدر والإصدار والتجميع من ZIP في أداة التغليف الأصلية.
- مشروع الواجهة الكامل لم يُبنَ هنا؛ `esbuild` غير مثبت في بيئة Linux الحالية.
- تشغيل PyInstaller/Inno Setup وقيام VS Code فعليًا على Windows **لم يتم التحقق منهما**.

## اختبار Windows الفعلي

1. فك السورس الكامل في مجلد جديد، أو طبّق الباتش على إصدار v2.31 السابق المحدد.
2. شغّل `BUILD_BARQ.bat` — لا تُشغّل `installer.iss` منفصلًا.
3. إذا ظهر فشل جديد احتفظ بالملف `release/python-tests.log` و `release/python-tests-failures.txt` وأرسل مخرجات الاختبارات مع traceback.

هذه معالجة لاختبارين محددين وليست ضمانًا بأن كل اختبارات Windows أو إنشاء المثبّت قد نجحت فعليًا.
