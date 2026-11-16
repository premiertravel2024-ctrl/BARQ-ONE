"""Recognize explicit user questions about videos ON THEIR OWN PC."""
from __future__ import annotations
import asyncio
import re
import sys

_LOCAL=re.compile(r'(?:على|علي|في|من)\s+(?:الـ?)?(?:الجهاز|الكمبيوتر|اللابتوب|الهارد|اللاب|عندي|جهازي)|\bon\s+my\s+(?:pc|computer|drive)\b',re.I)
_MEDIA=re.compile(r'فيلم|افلام|أفلام|أفلامي|فيديو|movies?|videos?',re.I)
_DISCOVER=re.compile(r'رشح|رشّح|اختار|اختارلي|شوف|دور|ابحث|قائمة|موجود|find|recommend|list|choose|show',re.I)

async def local_movie_reply(message:str)->str|None:
    if (not isinstance(message,str) or len(message)>350 or not
        (_LOCAL.search(message) and _MEDIA.search(message) and _DISCOVER.search(message))):
        return None
    from computer_control.api import load_policy
    policy=load_policy()
    if not policy.enabled:
        return 'أقدر أدوّر في الأفلام اللي على جهازك، بس محتاج تفعيل إذن التحكم في الكمبيوتر من إعدادات برق الأول. مش هفتح أو أرفع ملفات من غير إذنك.'
    if sys.platform!='win32':
        return 'قراءة ملفات الجهاز في النسخة دي محتاجة تشغيل برق على Windows.'
    from services.local_media import discover_movies
    found=await asyncio.to_thread(discover_movies,policy.allowed_folders)
    if not found['searched_folders']:
        return 'مفيش مجلدات أفلام متاحة. حدّد مكان أفلامك ضمن المجلدات المسموحة في إعدادات الكمبيوتر.'
    if not found['movies']:
        if found.get('status') in ('indexing','idle'):
            return 'فهرس الملفات المحلية لسه بيشتغل في الخلفية، ومش هقدر أقول إني فحصت الجهاز كله قبل ما يخلص.'
        return 'دورت في مجلدات الفيديو المسموحة وملاقيتش ملفات أفلام. ضيف مجلد الأفلام الصحيح في الإعدادات وخليني أدوّر تاني.'
    lines=['دورت في ملفات الفيديو المحلية، ودي نسخ موجودة فعلًا على جهازك:']
    for idx,item in enumerate(found['movies'][:7],1):
        lines.append(f"{idx}. {item['name']} — {item['quality']} — {item['size_gb']} GB")
    lines.append('ده ترتيب أولي حسب جودة النسخة وحجمها، مش تقييم لجودة الفيلم نفسه. تقدر تختار واحد أو تطلب مني أبحث عن تقييماته العامة.')
    if found['truncated']:lines.append('البحث اتحدد تلقائيًا لحماية أداء الجهاز؛ ممكن نضيّق نطاقه بمجلد معين.')
    return '\n'.join(lines)
