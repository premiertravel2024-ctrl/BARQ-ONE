# BARQ AI v2.30.0 — إصلاح توقف البناء عند Release Metadata Preflight

## سبب المشكلة

في تحديث مركز العمل تم تغيير `data-studio-version` إلى `v2.30.0-work-center-ui-audit`، بينما كان فحص الإصدار وسكربت التحقق من الحزمة المترجمة يتوقعان وجود `v2.30.0-build-gated-ui` داخل مكون `WorkspaceStudio.tsx` وفي JavaScript النهائي. لذلك توقف البناء قبل مرحلة npm.

## الإصلاح

تم الاحتفاظ بالعلامة الجديدة `data-studio-version`، وإضافة علامة مستقلة `data-release-marker="v2.30.0-build-gated-ui"` إلى نفس المكوّن. لم يتم تعطيل فحص الإصدار أو تخطي فحص React ولم تتغير هوية التثبيت أو صلاحيات البرنامج. أُضيفت اختبارات انحدار تتحقق من العلامتين وسلامة إصدار v2.30.0.

## طريقة البناء على Windows

1. فك ضغط ZIP كاملًا في مجلد جديد (وليس فوق سورس قديم).
2. شغّل `BUILD_BARQ.bat`.
3. سيظهر الفحص `BARQ release metadata and frontend lockfile are consistent.` ثم يكمل لمرحلة اختبارات React وتكوين EXE وInno Setup، إذا كانت جميع الاعتماديات متوفرة والاختبارات ناجحة.

إذا ظهرت مشكلة أخرى في `npm ci`، أو `esbuild`، أو `PyInstaller` أرسل سطور الخطأ الجديدة؛ هذا الإصلاح يعالج فشل فحص الإصدار تحديدًا ولا يضمن نجاح أي مرحلة لاحقة بلا اختبارها على Windows.

## التحقق

- `python scripts/verify_release_consistency.py` — يجب أن ينجح.
- `python scripts/verify_source_integrity.py` و `python scripts/audit_release_readiness.py` — فحوص مستقلة.
- `python -m pytest -q tests/test_v230_release_gate_workspace_marker.py tests/test_frontend_build_gate_v2142.py` — اختبارات إضافية.
- EXE نفسه غير مبني أو مُجرَّب في بيئة Windows الحقيقية هنا.
