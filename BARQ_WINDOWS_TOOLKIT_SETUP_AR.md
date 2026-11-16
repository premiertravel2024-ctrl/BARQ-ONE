# BARQ Windows Toolkit — تثبيت واحد وربط بالأدوات (v2.31)

## تثبيت الأدوات

افتح Windows PowerShell من مجلد السورس، ثم نفّذ **أمرًا واحدًا**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\INSTALL_BARQ_TOOLKIT.ps1
```

تجربة بدون تثبيت: `powershell -NoProfile -ExecutionPolicy Bypass -File .\INSTALL_BARQ_TOOLKIT.ps1 -PlanOnly`

السكريبت يفحص الموجود أولًا ولا يعيد تثبيته. يثبت الأدوات الناقصة من كتالوج WinGet الرسمي ويثبت Windows-MCP من `uv` في بيئة Python 3.14 منفصلة؛ يثبت LibreHardwareMonitor v0.9.6 من إصدار GitHub الرسمي بعد مقارنة SHA-256، داخل `%LOCALAPPDATA%\BARQ\toolkit\hardware-monitor`.

الأدوات: Git، GitHub CLI، Node.js LTS، VS Code، Python 3.11، PowerShell 7، 7-Zip، FFmpeg، ripgrep، fd، uv، Windows-MCP، LibreHardwareMonitor. الطقس والبحث موجودان داخل برق ويحتاجان الاتصال بالإنترنت وقت الاستخدام، وليس تثبيت أداة خارجية.

بعض حزم WinGet قد تطلب UAC أو تعجز عن التثبيت دون صلاحيات مستخدم مناسبة. لا يعطّل السكريبت حماية Windows ولا يطلب صلاحية Administrator من نفسه؛ تسجيل الدخول إلى GitHub/المصادر السحابية إن لزم يتم منفصلًا. عمليات تنزيل/تثبيت أدوات خارجية تظل تحت سياسة موافقات BARQ.

## التقرير

- `%LOCALAPPDATA%\BARQ\toolkit\installed-tools.json`: حالة وأماكن الأدوات.
- `%LOCALAPPDATA%\BARQ\toolkit\logs\install.log`: أخطاء التثبيت.

تقرير JSON **للعرض فقط** وليس مصدرًا لصلاحيات أو أوامر قابلة للتنفيذ.

## إيه اللي اتغيّر في السورس؟

- `core/tool_locator.py`: اكتشاف البرامج في PATH ثم مسارات تثبيتها القياسية المعروفة فقط (مش قراءة أوامر من ملف التقرير).
- `execution/runner.py`: اكتشاف أدوات Git وNode وVS Code وPowerShell الجديدة حتى لو التطبيق لا يرى PATH المحدث.
- `core/hardware_sensors.py`: اكتشاف مجلد LibreHardwareMonitor المشترك بعد التثبيت.
- `execution/doctor.py`: إظهار حالة Windows-MCP وuv وFFmpeg وripgrep وfd و7zip.

بعد تثبيت الأدوات: **اقفل برق وافتحه من جديد**. لو بتستخدم EXE قديم، لن يلتقط تحديث السورس وحده؛ ابني هذا السورس بـ `BUILD_BARQ.bat` ثم ثبّت الإصدار المبني. بعده شغّل `CHECK_BARQ_SENSORS.bat` لمعرفة إن كان حساس CPU فعليًا متاحًا. عدم ظهور CPU Temperature رغم وجود DLL قد يتطلب دعمًا من الجهاز/الدرايفر؛ لا تخترع القراءة.

## الاختبارات والحدود

تم اختبار كود Python والمواقع الثابتة وفحص سلامة السورس، لكن **لم يتم تشغيل Windows PowerShell أو winget أو البناء EXE على جهاز Windows داخل هذه البيئة**. أي نتيجة تثبيت على جهازك ستتضح من ملف التقرير المحلي.
