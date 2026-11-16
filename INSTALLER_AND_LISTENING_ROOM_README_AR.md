# BARQ ONE — غرفة الاستماع والمثبت

## دمج الكود

غرفة الاستماع متصلة بالواجهة (`frontend/src/App.tsx` و`Sidebar.tsx`) وبمسار FastAPI (`api_routes/listening_rooms.py`).

تتيح غرفة خاصة لشخصين، رمز ومفتاح دعوة، دردشة أثناء الاستماع، ومزامنة بيانات التشغيل لمصدر صوت HTTPS مباشر.

**قيد مهم:** سيرفر BARQ محلي على جهازك فقط؛ رابط الدعوة لا يفتح من جهاز آخر عبر الإنترنت حاليًا. تحتاج خدمة ربط آمنة مستقلة أو شبكة VPN وإعدادات مناسبة، ولا تعمل روابط صفحات Spotify/YouTube كمصدر صوت مباشر.

## بناء مثبت Windows

1. فك الـ ZIP على جهاز ويندوز 10/11 64-bit.
2. شغّل `UPLOAD_BARQ_ONE_AND_BUILD.bat` لرفع السورس على المستودع `premiertravel2024-ctrl/BARQ-ONE` (يتطلب Git وتسجيل الدخول لحساب GitHub المخوّل).
3. افتح https://github.com/premiertravel2024-ctrl/BARQ-ONE/actions ثم Workflow `BARQ — verified frontend and Windows installer`.
4. بعد نجاح `windows-x64`، افتح آخر Run ثم Artifacts وحمّل `BARQ-v2.37.2-verified-Windows-x64`.
5. داخله `BARQ_Setup_2.37.2.exe` والمخرجات المساعدة.

أو شغّل `BUILD_WINDOWS_EXE.bat` محليًا على ويندوز مع متطلبات المشروع، وراجع سجلات `release` في حالة الفشل.

**لم يتم إنتاج ملف EXE في بيئة تجهيز هذه الحزمة (Linux).** لا تعتبر الـ ZIP نفسه ملف مثبت.
