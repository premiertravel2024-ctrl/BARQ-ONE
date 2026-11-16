# تشغيل وبناء BARQ v2.18

هذه حزمة سورس؛ لا تحتوي مثبت Windows أو Portable مجرّبًا.

## Windows

1. ثبّت Python 3.11 x64 مع Python Launcher، وNode.js 22 LTS مع npm، وInno Setup 6. يحتاج التطبيق Microsoft Edge WebView2 Runtime.
2. فك الأرشيف في مسار قصير مثل C:\BARQ218، ثم افتح مجلد BARQ.
3. شغّل BUILD_BARQ.bat. يتولى سكربت البناء اختيار مسار عمل قصير وتثبيت الاعتماديات وإجراء الاختبارات قبل التغليف. يلزم اتصال لتنزيل الاعتماديات.
4. عند نجاح **جميع** المراحل، ستكون المخرجات في release: BARQ_Setup_2.18.0.exe وBARQ_Portable_2.18.0.zip، مع self-test.json وinstalled-self-test.json وrelease-evidence.json وعلامة build-ok-v2.18.0.marker.
5. لا تُعامل وجود EXE قديم أو نجاح pytest وحده كنجاح إصدار. راجع سجل windows-build.log ونتائج الفحوص وعلامة fresh-react. وضع recovery غير معتمد كإصدار جديد.
6. ثبّت Setup كتحديث عادي أو فك Portable في مجلد منفصل. لا تحذف مجلد بيانات %LOCALAPPDATA%\AI Router Agent؛ معرّف التثبيت ومسار البيانات ومفتاح التخزين المحلي محفوظة. يُستحسن نسخ مجلد البيانات احتياطيًا قبل أي ترقية.

## تشغيل المصدر والاختبارات

استخدم بيئة Python مستقلة، ثم python -m pip install -r requirements-test.txt. للواجهة: cd frontend ثم npm ci وnpm run typecheck وnpm run test:imports وnpm run test:frontend وnpm run test:chat وnpm run build. بعد انتهاء بناء React شغّل python -m pytest -q من مجلد BARQ؛ لا تشغّل pytest بالتوازي مع حذف وإعادة إنشاء web/react.

لتشغيل API محليًا: python -m uvicorn api:app --host 127.0.0.1 --port 8000. لتشغيل تطبيق المصدر المكتبي ثبّت requirements-desktop.txt ثم python desktop.py على Windows. مفاتيح المزودين تُضاف من الإعدادات أو .env محلي خاص، ولا تضعها في أرشيف السورس.

لاختبار واجهة المتصفح تحتاج Playwright ومتصفحًا مثبتًا، ثم شغّل scripts/ui_brain_smoke.py ضد API المحلي. يمكن تمرير --browser-config لملف JSON يحتوي executablePath وargs. هذا اختبار المصدر ولا يثبت نجاح EXE.
