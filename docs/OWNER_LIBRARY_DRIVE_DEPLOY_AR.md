# BARQ ONE — مكتبة المالك الخاصة (محلي + أونلاين)

## ما اتنفّذ في السورس

- على ويندوز: قاعدة SQLite مع WAL لفهرس الكتب والسلاسل، ومسارها G:\BARQ DATABASE\barq_library.sqlite3 إن كان الفولدر موجودًا، أو مجلد بيانات BARQ الخاص بالمستخدم. يمكن تثبيت المسار بمتغير BARQ_READING_DB_DIR.
- إدارة داخل إعدادات Drive: فهرسة الفولدر، إنشاء كروت السلاسل، ربط الأعداد وترتيبها. فتح PDF في BARQ زي السابق.
- برنامج BARQ المكتبي وواجهته FastAPI يفضلوا على 127.0.0.1 فقط؛ لا تنشر الخدمة الرئيسية على الإنترنت.
- للوصول البعيد: Cloudflare Worker مستقل مع D1، وتسجيل Google OpenID Connect لكل مستخدم. المستخدم العادي لا يُطلب منه أي إذن Google Drive.
- المالك الوحيد حسب OWNER_GOOGLE_EMAIL (ويُفضّل تقييد OWNER_GOOGLE_SUB) يربط نفس حسابه الأصلي بصلاحية drive.readonly. رمز تحديث الوصول مشفّر بـ AES-GCM في D1، والمفتاح محفوظ في Worker Secrets.
- أي ملف جديد غير منشور افتراضيًا. المالك يختار ما يُنشر ويربطه بالسلاسل ويرتب الأعداد. القرّاء يشاهدون المنشور فقط.
- قارئ PDF عبر المتصفح، وتنزيل الكتب المنشورة، وحفظ صفحة القراءة والمفضلة لكل مستخدم بمعرّف Google sub.
- الفهرس المحلي وقاعدة الإنترنت منفصلان أمنيًا. تعديلات المحلي لا تنتقل تلقائيًا إلى D1؛ إدارة الإنترنت ومزامنة Drive للأونلاين تتم من صفحة المالك. لا يوجد كشف تلقائي لكل ملفات Drive.
- يمكن إضافة عنوان Worker من إعدادات BARQ لتفعيل زر «المكتبة أونلاين».

## تهيئة المكتبة المحلية في ويندوز

1. احتفظ بالفولدر G:\BARQ DATABASE الموجود بالفعل.
2. اختياري: نفّذ في CMD:
   setx BARQ_READING_DB_DIR "G:\BARQ DATABASE"
3. أعد تشغيل BARQ ONE، واربط Google Drive من الإعدادات بحساب المالك كما كنت بتعمل.
4. افتح «إدارة المكتبة المحلية والسلاسل» واضغط «افهرس فولدر درايف». أنشئ السلاسل واربط الأعداد.

قاعدة SQLite بيانات وصفية، ولا تنسخ ملفات PDF إلى G، ولا يُخزَّن فيها مفتاح Google OAuth.

## إعداد خدمة القراءة على Cloudflare

يلزم حساب Cloudflare ومشروع Google Cloud مملوكان للمالك. لا توجد خدمة منشورة ولا توثيق Google فعلي ضمن تعديل السورس؛ هذه خطوات تفعيل المالك بنفسه.

1. فعّل Google Drive API وأنشئ Google OAuth Web application مختلفًا عن Desktop OAuth الخاص بتطبيق ويندوز.
2. أضف Authorized Redirect URI:
   https://YOUR-LIBRARY-DOMAIN/auth/callback
   واضبط Google OAuth consent screen للمستخدمين. نطاق drive.readonly حساس وقد يتطلب مراجعة Google عند إطلاق التطبيق للعامة.
3. أنشئ D1 في Cloudflare:
   npx wrangler d1 create barq-one-reading
4. عدّل ملف wrangler.library.toml بوضع BASE_URL وGOOGLE_CLIENT_ID وOWNER_GOOGLE_EMAIL ومعرّف D1 الصحيح (database_id). لا تضع أسرارًا في TOML.
5. ارفع الأسرار على حساب Cloudflare من الطرفية:
   npx wrangler secret put GOOGLE_CLIENT_SECRET --config wrangler.library.toml
   npx wrangler secret put SESSION_SECRET --config wrangler.library.toml
   npx wrangler secret put TOKEN_KEY_B64 --config wrangler.library.toml
   استعمل SESSION_SECRET عشوائيًا طويلًا، وTOKEN_KEY_B64 يحتوي 32 بايت عشوائية بصيغة base64url من دون padding. لا تنشر هذه القيم. ويمكن إضافة OWNER_GOOGLE_SUB كسرّ لتعزيز الربط بهوية المالك الثابتة.
6. أنشئ الجداول:
   npx wrangler d1 execute barq-one-reading --config wrangler.library.toml --remote --file cloudflare/library/schema.sql
7. انشر البوابة:
   npx wrangler deploy --config wrangler.library.toml
8. افتح رابط الخدمة وسجل الدخول بحساب Google المالك، ثم اضغط «اربط حسابك كمالك»، وامنح إذن Drive للمالك فقط.
9. ألصق رابط فولدر الروايات، واضغط تحديث الكتب، وأنشئ كروت السلاسل وانشر الكتب المسموح بها.
10. شارك رابط المكتبة مع القرّاء. كل شخص يسجل الدخول بحساب Google مختلف، بدون صلاحيات مباشرة على حساب Drive الخاص بك.
11. داخل BARQ ONE احفظ نفس رابط HTTPS من إعدادات المكتبة المحلية، لإظهار زر «المكتبة أونلاين».

## حدود الأمان والتشغيل

- لا تشارك أي مجلد شخصي من Drive مع المستخدمين ولا تمنحهم أي OAuth Token أو كلمة سر، ولا تعرّض BARQ FastAPI المحلي للإنترنت أو Cloudflare Tunnel.
- بوابة الإنترنت تعطي ملفات PDF وأغلفتها المسموح بها فقط عبر واجهات القراءة. هي ليست بروكسي عامة لحساب Drive.
- لا يوجد Service Account؛ وصول الكتب يكون من حساب Google الخاص بالمالك على السيرفر فقط.
- لا يكون الوصول البعيد متاحًا حتى يتم تفعيل Cloudflare D1 وGoogle OAuth ونشر Worker بالفعل.
- القارئ الأونلاين يحفظ آخر صفحة يحددها المستخدم يدويًا والمفضلة؛ لا يتتبع تلقائيًا التمرير داخل PDF المدمج.
- خدمة Cloudflare/Google تخضع لحصص وقيود خطط الاستخدام الخاصة بهما. راجع الخطط قبل الإطلاق.
- احتفظ بنسخ احتياطية من SQLite وD1، ولا تفقد TOKEN_KEY_B64 وإلا سيحتاج المالك إعادة ربط Drive.

## اختبارات مطلوبة

python -m pytest -q tests/test_reading_local_library.py
node --check cloudflare/library/worker.mjs
node --test cloudflare/library_worker.test.mjs
python scripts/verify_release_consistency.py
cd frontend && npm ci && npm run build

## حالة الإصدار

السورس مبني على فرع أسترا private-drive-profile-sync، وليس main القديم. الإصدار المستهدف 2.41.19 لأن قناة التحديث الموقّع تعرض 2.41.18 بالفعل، وسجل GitHub Actions السابق أثبت أن نشر إصدار موجود بملف تثبيت مختلف يتم منعه أمنيًا. لا يُعد المثبت جاهزًا إلا بعد اختبارات Windows والنشر الفعلي.
