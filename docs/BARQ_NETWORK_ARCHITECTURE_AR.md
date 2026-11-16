# ملفات شبكة BARQ — هيكل وشرح مختصر

```text
command_network/
  contracts.py     # Pydantic Request, TaskProfile, RoutePlan, Event, TaskGraph
  registry.py      # provider config + models.yaml capabilities
  triage.py        # Arabic/English rules + similarity examples + privacy indicators
  control.py       # quota counters + breaker states
  routing.py       # hard filters, task scoring, safe fallback chain
  cache.py         # bounded exact in-memory cache + in-flight coalescing
  planner.py       # validate DAG and safely dispatch independent callbacks
  verifier.py      # cheap format/language/content checks
  trace.py         # redacted local traces and p50/p95 aggregations
  service.py       # CommandNetwork network layer plugged into legacy Engine
config/models.yaml
config/task_types.yaml
config/policies.yaml
examples/triage.jsonl
scripts/barq_network_benchmark.py
tests/test_command_network_v28.py
frontend/src/components/network/NetworkMap.tsx
```

## المسار الفعلي
User → Brain persona/intent → Engine → CommandNetwork.prepare → Registry/Triage/Router → Engine original safe candidates → single model with fallbacks → Brain reply validation → trace. Existing approval checks own every file/tool write.

## الإعدادات
- إضافة موديل: أضفه أولًا في `config/providers.yaml` داخل المزود المصرح به؛ أضف capability override اختياريًا في `config/models.yaml` بنفس المعرف `provider/model`.
- لا ترفع مفاتيح API مع الملفات؛ خزّنها في Windows Credential Manager أو env، وتحقق من شروط الحصة المجانية.
- لضبط الجودة/السرعة، غيّر `mode_weights` في `config/policies.yaml` (quality/latency/availability/reliability)، ثم راجع نتائج `python scripts/barq_network_benchmark.py`.
- Disabled/draining/pinned تؤثر على اختيارات الشبكة، لكن يجب حفظ متطلبات القدرة الحقيقية (vision/json/native tools) في Registry؛ لا تعلن قدرة غير موثوقة.
- `local-only` يمنع السحابة، ولا يعني أن Ollama مثبت تلقائيًا.

## حدود وثقة النتائج
القيم الافتراضية لقوة النماذج تقديرية، وليست تقييم أداء مثبتًا. النماذج الاصطناعية في benchmark مخصصة لاختبار قرار التوجيه فقط. تقارير الجودة لا تكفي لتقرير صحة رد حقيقي أو أمان أمر Shell. لا يوجد تنفيذ أدوات دون موافقة النظام القائمة.

## مسؤوليات الموديولات (10 نقاط لكل موديول)

### contracts.py
1. عقود ثابتة للطلب والمهمة والخطة والحدث.
2. Pydantic يرفض الأدوار غير المعروفة.
3. يضع حدًا لطول المحادثة والمرفقات.
4. يعرّف أوضاع السرعة الثلاثة.
5. يحدد وضع الخصوصية المحلي.
6. ينقل هوية request_id.
7. يحفظ وصف ملف أو صورة كمدخل.
8. يفرض قيم TaskProfile الصريحة.
9. يتحقق من دورات TaskGraph وعمقه.
10. لا ينفذ أدوات ولا يتصل بموديلات.

### registry.py
1. يقرأ إعدادات مزودي BARQ الحالية.
2. يضيف capability override اختياريًا.
3. يراقب تعديل models.yaml أثناء العمل.
4. يعتبر القدرات غير المعلنة غير مدعومة.
5. يخزن نطاق السياق وطريقة الوسائط.
6. يخزن المؤشرات التقديرية للسرعة.
7. يفصل الجودة العربية عن بقية الدرجات.
8. يحتفظ بمعلومات حدود RPM/RPD/TPM.
9. لا يتجاوز قواعد المدفوع والمزود المحلي القديمة.
10. لا يتحقق وحده من إتاحة مزود عبر الشبكة.

### triage.py
1. يقرأ آخر رسالة مباشرة من المستخدم.
2. يميز الأحرف العربية والإنجليزية.
3. يفحص مؤشرات الكود وإصلاح الأخطاء.
4. يميز الترجمة والكتابة والتلخيص.
5. يميز مرفقات الصور عن النصوص.
6. يقدر كلفة السياق بعدد الأحرف.
7. يصنف الصعوبة إلى ثلاث درجات.
8. يستخدم أمثلة محلية مع تشابه نصي.
9. يتحقق مبدئيًا من أسرار وبيانات شخصية.
10. لا يستخدم موديل تصنيف خارجي تلقائيًا.

### routing.py
1. يفحص بيانات الخصوصية أولًا.
2. يرفض النموذج غير المجهز أو المعطل.
3. يفحص طول السياق والمتطلبات الصريحة.
4. يوزن درجة الجودة حسب نوع المهمة.
5. يراعي تفضيل السرعة أو الجودة.
6. يراعي موثوقية الردود المحلية المقاسة.
7. يسمح باستكشاف محدود للمهام العادية.
8. يتجنب تكرار مزود قريبًا قدر الإمكان.
9. يحافظ على Ollama آخر سلسلة cloud-first.
10. تعبر strategy عن خطة لا تنفيذ متوازٍ بعد.

### control.py
1. يطبق عداد طلبات لكل مزود.
2. يحتفظ بتاريخ طلبات لمدة يوم.
3. يفحص الحصص الدقيقة إن كانت معروفة.
4. يوفر هامش أمان للحصص الصغيرة.
5. يحسب حد الطلبات في الدقيقة.
6. يحسب حد الطلبات في اليوم.
7. يحسب حد الرموز عند تقديرها.
8. يفتح CircuitBreaker بعد تكرار الفشل.
9. يراعي نجاح probe وحالة half-open.
10. هذه أرقام محلية لا رصيد موثق من API.

### cache.py
1. مخزن مطابقات تامة داخل الذاكرة.
2. لا يحفظ أي ملفات سرية افتراضيًا.
3. يستخدم hash لتمثيل محتوى المفتاح.
4. يفصل المفاتيح بوضع التوجيه.
5. يطبق TTL على العناصر.
6. يحذف الأقدم عند بلوغ الحد.
7. يمنع تنفيذ العمليات المكررة أثناء الطيران.
8. يحمي العمليات المشتركة من إلغاء مستهلك واحد.
9. فئة مفيدة للاختبار والتوسع.
10. التكامل الإنتاجي والدلالة المحلية لم يكتمل.

### planner.py
1. يعتمد على TaskGraph بعد التحقق.
2. يرفض عقد الاعتماد الدوري.
3. يفحص اعتماد العقد على مفاتيح صالحة.
4. يشغل المستقل منها معًا.
5. يحدد التوازي عبر semaphore.
6. يعطي كل عقدة مخرجات تبعياتها فقط.
7. ينتظر نهاية الدفعة المستقلة.
8. يجمع النتائج في قاموس.
9. لا يشغّل أوامر النظام بنفسه.
10. ربطه بمحرك agent يحتاج مرحلة تنفيذ منفصلة.

### verifier.py
1. يفحص أن الرد نص غير فارغ.
2. يتحقق من JSON عند طلبه.
3. يفحص وجود العربية حين تكون ضرورية.
4. يرفض تجاوز حد طول الرد.
5. يعيد سبب الفحص.
6. يعيد رقم ثقة تقريبيًا.
7. لا يضمن صحة الحقائق.
8. لا يشغّل كود النماذج بلا sandbox.
9. لا يستخدم نموذج Judge إضافيًا.
10. الحفاظ على فاحص هوية BARQ الأصلية مسؤولية Brain.

### trace.py
1. يحفظ request_id وتوقيت المراحل.
2. لا يحفظ النصوص السرية للمحادثات.
3. يحتفظ بآخر 200 طلب.
4. يسمح بأحداث متعددة لكل طلب.
5. يرصد اختيار الموديل.
6. يرصد حالات الإخفاق النهائية.
7. يجمع مدد المراحل إن سجلت.
8. يحسِب وسطاء p50 وp95.
9. يعرض تاريخًا محليًا ينتهي بإغلاق التطبيق.
10. لا يرسل telemetry لأي جهة.

### service.py
1. يربط العقود بالمحرك القديم.
2. ينشئ Registry وTriage وRouter.
3. ينشئ Quota وBreaker وCache.
4. يهيئ TraceStore مستقلًا.
5. يحدد الخصوصية الفعالة.
6. يحافظ على قائمة المرشحين المصرح لهم.
7. يوفر واجهة أحداث typed.
8. يعرض خريطة الموديلات.
9. لا يمنح صلاحية للملفات أو الأوامر.
10. حالات متقدمة لا تزال تخطيطية كما موضح في الإصدار.
