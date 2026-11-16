"""Classify real failures; never invent dependencies or silently install them."""
import re

def classify_failure(error):
    text=str(error).lower()
    if re.search(r'no module named|modulenotfounderror|not installed|interpreter unavailable',text):
        return {'kind':'environment','action':'راجع الاعتماد الناقص في بيئة المشروع؛ التثبيت يحتاج موافقة منفصلة، ولا يتصلح بتغيير الكود عشوائيًا.'}
    if re.search(r'429|quota|rate.limit|cooldown',text):
        return {'kind':'quota','action':'انتظر مدة التهدئة أو استخدم بديلًا مجانيًا متاحًا؛ الملفات المحفوظة لن يعاد تنفيذها.'}
    if re.search(r'network|connect|timeout|timed out|مهلة',text):
        return {'kind':'connection','action':'إعادة المحاولة من نفس الملف مع انتظار محدود؛ راجع الاتصال أو النموذج المحلي لو استمر العطل.'}
    if re.search(r'context too small|context.*limit',text):
        return {'kind':'context','action':'المطلوب أكبر من سياق النموذج المتاح؛ استخدم سياقًا أكبر يناسب الجهاز أو قسّم المتطلب.'}
    if re.search(r'assert|syntax|invalid|incomplete|output limit|failed|missing_local',text):
        return {'kind':'code','action':'إصلاح الجزء المسؤول بناءً على الكود والخطأ، ثم إعادة الاختبار بعد حفظ التعديل.'}
    return {'kind':'review','action':'راجع تفاصيل الخطأ الفعلية قبل تكرار العملية.'}
