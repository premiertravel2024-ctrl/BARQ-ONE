# إصلاح فشل ensurepip أثناء بناء BARQ v2.31.0

## ما الذي حدث؟
بناء React نجح، لكن تنفيذ `py -3.11 -m venv .buildvenv` توقف لأن استدعاء ensurepip داخل Python رجع exit 1. الرسالة وحدها لا تحدد هل السبب تثبيت Python ناقص، برنامج حماية، صلاحيات كتابة، أو ملفات Temp.

## التعديل
- البناء يشغّل `scripts/create_build_venv.py` بدل الاعتماد على محاولة venv واحدة.
- يحاول venv القياسي أولاً باستخدام Python 3.11.
- لو ensurepip فشل، يحاول `uv venv --seed --python <Python3.11>` في البيئة المعزولة. يكتشف uv أيضًا داخل `%USERPROFILE%\.local\bin` حتى لو PATH قديم.
- إذا uv غير متاح/فشل، ينشئ venv بـ `--without-pip` ويستخدم pip الأساسي مع `--python <venv>` لتثبيت pip **داخل** venv فقط.
- قبل استكمال البناء، يتأكد أن Python داخل venv إصدار 3.11 وأن `pip` قابل للاستيراد.
- يكتب التشخيص في `release/python-venv-setup.log` وينقل السجل من مجلد البناء المؤقت إلى `release` في مجلد السورس الأصلي عند الفشل. عند فشل جميع الطرق يتوقف البناء، ولا يتجاوز اختبارات Python أو المثبّت.

## اختبار على Windows من غير إعادة بناء React
شغّل `CHECK_BARQ_PYTHON_VENV.bat` من مجلد BARQ. الاختبار ينشئ بيئة تجريبية مؤقتة ثم يحذفها وينقل سجل النتيجة إلى `release/python-venv-probe.log`.

## لو فشل الاختبار
افتح السجل، وتحقق من Python 3.11 x64 و uv (`uv --version` أو `%USERPROFILE%\.local\bin\uv.exe --version`)، وWindows Defender، ومساحة القرص، وصلاحية الكتابة في `%LOCALAPPDATA%\Bq`. لا تشغّل البناء كمسؤول إلا عند الحاجة الفعلية؛ الإصلاح لا يتطلب Admin عادةً.

## حدود التحقق
أجريت اختبارات وحدات ومحاكاة لانقطاع ensurepip وفحوص سورس الحزمة على Linux. **لم يتم تشغيل اختبار venv باستخدام Python 3.11 على Windows في هذه البيئة، ولم يتم تأكيد نجاح EXE الفعلي بعد التعديل.**
