# حل مشكلة عدم رفع BARQ ONE إلى GitHub

المستودع المستهدف: https://github.com/premiertravel2024-ctrl/BARQ-ONE

## الطريقة الأولى: سكربت الرفع المحسن

1. فك ضغط المشروع بالكامل في مجلد عادي، مثل C:\BARQ-ONE. لا تشغّل ملف BAT من داخل نافذة ZIP.
2. تأكد من تثبيت Git for Windows: https://git-scm.com/download/win
3. شغّل `UPLOAD_BARQ_ONE_FIXED.bat` بالضغط مرتين.
4. إذا ظهر طلب تسجيل الدخول في المتصفح، سجّل الدخول بحساب premiertravel2024-ctrl.
5. إذا نجح الرفع سيظهر `SUCCESS: GitHub main now points to ...`، وتُفتح صفحة GitHub Actions.
6. إذا فشل، انسخ محتوى `%TEMP%\BARQ-ONE-UPLOAD-LOG.txt` أو صوّر آخر رسالة خطأ وأرسلها.

لا تطلب فتح Terminal كمسؤول؛ لا توجد حاجة عادةً لصلاحية Administrator لرفع ملفاتك.

## الطريقة الثانية: GitHub Desktop بدون أوامر

1. ثبّت GitHub Desktop، وسجّل دخولك إلى حساب premiertravel2024-ctrl.
2. من File > Clone repository اختر BARQ-ONE وحدد مجلدًا جديدًا على جهازك.
3. انسخ محتويات مجلد السورس المفكوك إلى مجلد المستودع المستنسخ. لا تنسخ ملفات `.git` من مصدر آخر إن وجدت.
4. افتح GitHub Desktop، واكتب وصفًا للتعديل، ثم اضغط Commit to main وبعدها Push origin.
5. افتح https://github.com/premiertravel2024-ctrl/BARQ-ONE/actions وتابع Workflow الخاص ببناء Windows.

## تنبيه

وجود السورس على GitHub لا يعني تلقائيًا نجاح بناء مثبت EXE. بعد الرفع، يجب أن تنجح مهام GitHub Actions ويظهر الـ Artifact المسمى BARQ-v2.37.2-verified-Windows-x64.
