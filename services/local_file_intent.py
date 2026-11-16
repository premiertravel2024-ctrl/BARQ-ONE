"""Read-only filename search for explicit requests about the users own device."""
from __future__ import annotations
import re
import sys
import asyncio

_LOCAL=re.compile(r'(?:جهازي|عندي|الكمبيوتر|الهارد|اللابتوب|اللاب|الجهاز|الملفات|الموجود عندي|عندنا|على الويندوز|على ويندوز|على الديسك|my pc|my computer|my files)',re.I)
_FIND=re.compile(r'(?:دور|ابحث|دورلي|ابحثلي|لاقيل[يى]|فين|فتش|شوف|هات|عايز|عاوز|محتاج|وريني|طلعلي|طلّعلي|رشح|اختار|find|search|locate|look for)',re.I)
_ITEM=re.compile(r'(?:ملف|مجلد|ملفات|صور|صورة|الصورة|pdf|word|اكسيل|excel|فيديو|صورتي|مستند|فاتورة|تقرير|مشروع|documents?|files?|folders?|pictures?|reports?)',re.I)

async def local_file_reply(message:str)->str|None:
    if not isinstance(message,str) or not 4<=len(message)<=350 or not (_LOCAL.search(message) and _FIND.search(message) and _ITEM.search(message)):
        return None
    if sys.platform!='win32':return 'البحث في ملفات الكمبيوتر متاح لما برق يكون شغال على Windows.'
    from computer_control.api import load_policy
    policy=load_policy()
    if not policy.enabled:return 'إذن الكمبيوتر مقفول. فعّل التفاعل مع الجهاز من إعدادات برق.'
    from services.device_index import search
    terms=re.sub(r'(?:يا برق|دورلي|دور|ابحثلي|ابحث|شوف|هات|فين|عايز|عاوز|محتاج|وريني|طلعلي|رشحلي|على|علي|في|من|جهازي|الجهاز|الكمبيوتر|الهارد|عندي|الملفات|ملف|مجلد)', ' ',message,flags=re.I).strip()
    if len(terms)<2:return 'قولي جزء من اسم الملف علشان أدوّر عليه في الفهرس المحلي.'
    result=await asyncio.to_thread(search,terms,allowed_folders=policy.allowed_folders)
    if result['status']=='permission_required':return 'فهرسة ملفات الجهاز مقفولة. فعّلها مرة واحدة من إعدادات التحكم في الكمبيوتر.'
    if result['status'] in ('indexing','idle') and not result.get('results'):
        return 'فهرس الملفات لسه بيجهز في الخلفية. هقدر أدور في الملفات بعد ما يخلص، من غير ما أفتّش الجهاز كله في كل سؤال.'
    if not result.get('results'):return 'ما لقيتش ملف مطابق في الفهرس الحالي. تقدر تحدّثه أو تراجع اسم الملف.'
    lines=['دورت في فهرس جهازك المحلي، ودي النتائج اللي لقيتها:']
    for i,item in enumerate(result['results'][:10],1):lines.append(f"{i}. {item['name']} ({item.get('extension','ملف')})")
    lines.append('دي نتائج أسماء ملفات فعلية، مش قراءة لمحتوى الملفات. لو تحب تفتح واحدة، اطلبها بالاسم وهتطبق موافقات الجهاز.')
    return '\n'.join(lines)
