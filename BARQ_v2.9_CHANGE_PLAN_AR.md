# خطة BARQ v2.9 (15 سطرًا)
1. router/config.py + core/models.py: عقود مجانية ومهاجرة إعدادات المستخدم دون فقد تفضيلاته.
2. config/free_allowlist.yaml + config/providers.yaml: قائمة السماح والمنع المثبتة داخل الحزمة.
3. providers/discovery.py + core/secrets.py: حصر مضيفي API وأسماء المفاتيح في الكتالوج الأصلي.
4. providers/client.py + providers/streaming.py: التعرّف على أخطاء الدفع وإيقاف المزود بشكل دائم.
5. router/engine.py + router/select.py: تطبيق Free Guard وتوجيه الحصص على الطلب الفعلي.
6. router/quota.py + router/limits.py + command_network/control.py: حصة مشتركة SQLite لكل موديل ونطاق حساب.
7. command_network/{registry,routing,service}.py: تطبيق حصص القدرات والتوجيه الآمن.
8. api.py: واجهة تدقيق مجاني بلا اتصالات سحابية، وتأكيد لإزالة حظر الفواتير.
9. frontend/src/components/workspace/ModelControls.tsx: فحص مجاني وبيانات الخصوصية.
10. config/models.yaml + config/policies.yaml: درجات قدرة متحفظة وإعداد توجيه البرمجة.
11. command_network/cache.py + triage.py + verifier.py: تحسينات محلية اختيارية للفهم والتحقق.
12. examples/triage.jsonl: أمثلة عربية/مصرية/فرانكو/إنجليزية موثقة ومختبرة.
13. tests/test_free_guard_v29.py: اختبارات أمان وحصص وتوافق ورجوع.
14. CLOUD_MODELS_GUIDE_AR.md + BARQ_v2.9_FREE_GUARD_AR.md: دليل وإصدار وقيود.
15. بناء Linux Python/Frontend إن توفّر؛ عدم الادعاء باختبار EXE Windows.
