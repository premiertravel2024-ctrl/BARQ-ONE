# BARQ AI v2.30.0 — إصلاح فشل اختبار حفظ المهمة على Windows

## الخطأ المبلغ عنه

توقف `BUILD_BARQ.bat` عند اختبار:

`tests/test_computer_checkpoints_v231.py::test_invalid_db_no_execution_on_persist_failure`

بعد نجاح 138 اختبارًا سابقًا. وضع البناء الصحيح هو التوقف إذا فشل اختبار يحمي تنفيذ المهام.

## السبب

كان مسار `TaskStateStore._connect()` يتحقق من وجود قاعدة البيانات بفرع مختلف حسب نظام التشغيل. عند توجيه قاعدة البيانات عمدًا إلى مجلد غير موجود:

- Linux: فرع الإنشاء الآمن يستخدم `os.open` ويرفع `OSError`؛ الاختبار ينجح.
- Windows: `sqlite3.connect` يرفع عادةً `sqlite3.OperationalError`، وهي ليست صنفًا فرعيًا من `OSError`؛ الاختبار يفشل.

الاختلاف في *نوع الخطأ*، وليس دليلًا على أن برق نفذ أمر الكمبيوتر قبل حفظ المهمة.

## التعديل

- `computer_control/state_store.py`: فحص صريح لوجود مجلد قاعدة البيانات وأنه مجلد بالفعل قبل كل اتصال. عند غيابه، يرفع `FileNotFoundError` عبر كل المنصات، وعند كونه ملفًا، يرفع `NotADirectoryError`.
- `tests/test_computer_checkpoints_v231.py`: اختبارات تحاكي فرع Windows وتتحقق أن المهمة لم تبدأ عند وجود مسار خاطئ.
- **لم نغير** ضرورة نجاح حفظ الـcheckpoint قبل تعيين مهمة نشطة، ولم نعطل اختبارًا أو نقصر بوابة البناء.

## نتائج التحقق هنا

- **39/39 نجاح** في اختبارات checkpoint وcomputer control وcognition وtest gate.
- نجح `python scripts/verify_source_integrity.py`.
- نجح `python scripts/verify_release_consistency.py`.
- تم تشغيل اختبار موسع لكنه لم يكتمل داخل المهلة المتاحة هنا؛ ظهرت إخفاقات أخرى في اختبارات تعتمد على أدوات غير متاحة في هذه البيئة، ومنها `esbuild`. لا يمكن اعتبار كل اختبارات Windows أو بناء EXE ناجحة بعد.

## التثبيت

1. اغلق نافذة البناء القديمة.
2. خذ نسخة احتياطية من السورس الحالي ثم فك ZIP الإصلاح الصغير في جذر مشروع BARQ، بجانب `BUILD_BARQ.bat`، وافق على استبدال الملفات.
3. شغّل `BUILD_BARQ.bat` مرة أخرى.
4. إذا ظهر اختبار فاشل جديد، سيظهر اسمه في نافذة البناء وفي `release/python-tests.log`، ومعه آخر اختبار في `release/python-tests-last-test.txt`.

**ملاحظة:** لا تشغل `installer.iss` مباشرة قبل تكوين `BARQ.exe`.
