# BARQ v2.6.1 — السورس الكامل

هذا الأرشيف يحتوي على أحدث نسخة متاحة من **الكود المصدري** لمشروع BARQ، وليس ملف EXE مبنيًا.

## المحتويات

- `frontend/` — واجهة React + TypeScript + Vite، المكوّنات والتصميم واللغات.
- `web/` — واجهة HTML الاحتياطية والملفات الثابتة.
- `brain/` — هوية برق، فهم الطلب، سجل المهمة، إدارة التوجيه والمتابعة.
- `api.py` و`router/` و`providers/` — خادم Python ومحرك توجيه النماذج.
- `agent/` و`coding/` و`workspace/` — مهام البرمجة وإدارة المشاريع.
- `voice/` و`tools/` و`github/` و`build/` — الصوت والأدوات وتكامل Git والبناء.
- `config/` و`core/` و`cache/` — الإعدادات والمنطق والبيانات المحلية.
- `assets/` و`frontend/public/brand/` — أيقونات وشعار BARQ من ملفات المشروع.
- `tests/` — اختبارات المصدر.
- `scripts/` و`BUILD_WINDOWS_EXE.bat` و`.github/workflows/` — إعدادات Windows وبناء الحزم.
- `.env.example` و`requirements*.txt` و`README.md` — التبعيات والتعليمات.

## التشغيل على Windows

1. فك الضغط.
2. افتح المجلد `BARQ_Source`.
3. ثبّت **Python 3.11** و**Node.js** (ومع إنشاء مثبت Windows ثبّت **Inno Setup 6**).
4. لواجهة React: افتح PowerShell داخل `frontend` وشغّل `npm install` ثم `npm run build`.
5. لتشغيل Python: من جذر المشروع شغّل `py -3.11 -m pip install -r requirements.txt` ثم `py -3.11 -m uvicorn api:app --host 127.0.0.1 --port 8000`.
6. لإنشاء مثبت Windows على Windows شغّل `BUILD_WINDOWS_EXE.bat` واتّبع `WINDOWS_BUILD_GUIDE_AR.md`.

## الحفاظ على البيانات

المشروع يحتفظ **بمعرّف التطبيق السابق** ومسار بيانات المستخدم في `%LOCALAPPDATA%\AI Router Agent` لقراءة المحادثات والإعدادات السابقة. لا تنقل أو تنسخ قواعد بيانات المستخدم إلى أرشيف السورس.

## مستثنيات مهمة

- **الخطوط الخاصة** مثل GE SS Two غير مرفقة، ولا يجوز إعادة توزيعها من بيئة العمل. احتفظ بالنسخة المرخّصة الموجودة على جهازك أو استخدم الخط الاحتياطي المذكور بالكود.
- مفاتيح API الحقيقية وملف `.env` وبيانات المستخدم والتخزين المؤقت ومجلدات البناء `dist`, `release`, `node_modules`, `.buildvenv` غير مرفقة عمدًا.
- ملف `frontend/package-lock.json` مرفق لتثبيت تبعيات الواجهة باستخدام `npm ci`.
- واجهة React المبنية مرفقة في `web/react`، ويمكن إعادة بنائها من المصدر.
- لم يتم بناء أو تجربة EXE جديد في بيئة تجميع الأرشيف هذه؛ الأرشيف مصدر قابل للبناء وليس مثبتًا جاهزًا.

راجع `SOURCE_MANIFEST.json` لعدد الملفات وبصمات SHA-256.
