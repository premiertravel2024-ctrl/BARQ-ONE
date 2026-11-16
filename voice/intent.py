"""Local interpretation of actual user speech; no model-generated arguments."""
from __future__ import annotations
import re
from voice.command_guard import normalize


_LEAD_IN = re.compile(
    r'^(?:(?:يا )?(?:برق|برء|barq)(?: ai)?|بقولك ايه|بقولك|بص بقى|بص بقي|طيب بص|طب بص|اسمعني|بص|طيب|طب|'
    r'لو سمحت|من فضلك|بعد اذنك|معلش|ممكن|ينفع|تقدر|عاوزك|عايزك|محتاجك|'
    r'انا عاوزك|انا عايزك|كنت عاوزك|كنت عايزك|please|can you|could you) +'
)


def _without_lead_in(value: str) -> str:
    value = ' '.join(value.split())
    while match := _LEAD_IN.match(value):
        value = value[match.end():]
    return value


def command_text(text:str)->str:
    """Normalize conversational lead-ins and the verb for classification."""
    value = _without_lead_in(normalize(text))
    # Map verbs used in requests, including common "-لي" or "-لّي" clitics.
    aliases={
        'تفتح':'افتح','تفتحلي':'افتح','تفتحلى':'افتح','افتحلي':'افتح',
        'تشغل':'شغل','تشغلي':'شغل','تشغللي':'شغل','شغلي':'شغل','شغللي':'شغل','فتحلي':'افتح',
        'تقفل':'اقفل','تقفللي':'اقفل',
        'تدور':'دور','تدورلي':'دور','دورلي':'دور',
        'تشوف':'شوف','تشوفلي':'شوف',
        'تبحث':'ابحث','تبحثلي':'ابحث','ابحثلي':'ابحث','فتشلي':'دور',
        'اقرالي':'اقرا','تقرالي':'اقرا','قفللي':'اقفل','اقفللي':'اقفل','وريني':'شوف',
        'تجيب':'هات','تجيبلي':'هات','هاتلي':'هات',
        'تنقل':'انقل','تنقللي':'انقل',
        'تنسخ':'انسخ','تنسخلي':'انسخ',
        'تمسح':'امسح','تمسحلي':'امسح',
        'تظبط':'ظبط','تظبطلي':'ظبط','ظبطلي':'ظبط','اضبطلي':'اضبط',
        'تضبط':'اضبط','تضبطلي':'اضبط',
        'تكتب':'اكتب','تكتبلي':'اكتب',
        'تعمل':'اعمل','تعمللي':'اعمل','اعملي':'اعمل','اعمللي':'اعمل','انشئلي':'انشئ','سوي':'اعمل','تسوي':'اعمل','سو':'اعمل','اعملنا':'اعمل',
        'صغرلي':'صغر','كبرلي':'كبر','اقفلها':'اقفل',
        'تثبت':'ثبت','تثبتلي':'ثبت',
        'تنزل':'نزل','تنزللي':'نزل','تنزلي':'نزل','نزللي':'نزل',
        'تحمل':'حمل','تحمللي':'حمل','تحملي':'حمل','حمللي':'حمل',
        'تسطب':'سطب','تسطبلي':'سطب','سطبلي':'سطب',
        'توقف':'وقف','توقفلي':'وقف','وقفلي':'وقف',
        'تكمل':'كمل','تكمللي':'كمل',
    }
    words=value.split()
    if words:words[0]=aliases.get(words[0],words[0])
    return ' '.join(words)


def command_target(text: str) -> str:
    """Return the raw text after the request verb, preserving file names and URLs."""
    words = re.finditer(r'[\w\u064b-\u065fـ]+', text)
    normalized = normalize(text).split()
    body = _without_lead_in(normalize(text)).split()
    if not body:
        return ''
    verb = next((match for i, match in enumerate(words) if i == len(normalized) - len(body)), None)
    if verb is None:
        return ''
    return text[verb.end():].strip(' \t،,؟?!؛:')


def non_executable(text:str)->bool:
    value=command_text(text)
    if re.fullmatch(r'(?:افتح|شغل|اقفل) (?:برامج|البرامج|تطبيقات|التطبيقات|ملفات|الملفات|مجلدات|فولدرات|apps|files|folders)', value):
        return True
    return bool(re.match(r"^(?:مت\w+ش|مات\w+ش|ما ت\w+ش|لا (?:تفتح|تشغل|تنفذ|تعمل|تحذف|تمسح|تبني)|مش (?:عاوزك|عايزك)|ازاي|كيف|اشرح|ترجم|هل|لو (?:قلت|طلبت)|افترض|مثلا|how|explain|translate|hypothetically|do not|don t)\b",value))


def has_action(value:str)->bool:
    return bool(re.search(r'(?<!\w)(?:افتح|شغل|اقفل|قفل|انقل|انسخ|الصق|امسح|احذف|رتب|اعمل\w*|انشئ\w*|ابني\w*|برمج\w*|ثبت|نزل|عدل|اكتب|نفذ|اضغط|دوس|بدل|حرك|صور|احفظ|اقرا|شوف|ابحث|دور|build|install|create|open|close|copy|move|delete|click|type|save|switch|run|search|find)(?!\w)',value))


def is_multi_step(value:str)->bool:
    # Common attached Egyptian conjunctions as well as English sequences.
    return bool(re.search(r'(?:وبعدين|و بعدين|ثم|بعد كده|\bthen\b|\band\s+(?:open|close|run|copy|move|delete|save|click|install|create|play)\b|(?:^|\s)و ?(?:افتح|شغل|اعمل|اكتب|احفظ|انقل|انسخ|امسح|احذف|ثبت|نزل|عدل|رتب|انشئ|اضغط|دوس|اقفل))',value))


def setting_request(text:str)->dict|None:
    value=command_text(text)
    setting='brightness' if any(x in value for x in ('سطوع','اضاءه','brightness')) else 'volume' if any(x in value for x in ('الصوت','صوت الجهاز','volume')) else None
    if setting is None:return None
    up=bool(re.match(r'(?:علي|اعلي|زود|ارفع|up|raise|increase)\b',value))
    down=bool(re.match(r'(?:وطي|قلل|انقص|اخفض|down|lower|decrease)\b',value))
    absolute=bool(re.match(r'(?:اضبط|خلي|ظبط|اجعل|set)\b',value))
    read=bool(re.search(r'(?<!\w)(?:كام|مستوي|get|what|level)(?!\w)',value))
    if not any((up,down,absolute,read)):return None
    if (up and re.search(r'\bو ?(?:وطي|قلل|انقص|اخفض)\b', value)) or (down and re.search(r'\bو ?(?:علي|اعلي|زود|ارفع)\b', value)):
        return {'error':'قول أزود ولا أقلل المستوى؟'}
    numbers=re.findall(r'\d+',value)
    if len(numbers)>1:return {'error':'قول نسبة واحدة واضحة من صفر لمية.'}
    if re.search(r'[-−]\s*\d|\d[.,٫]\d',text):
        return {'error':'قول نسبة صحيحة من صفر لمية.'}
    if read and not any((up,down,absolute)):return {'setting':setting,'action':'get'}
    if absolute:
        percent = int(numbers[0]) if numbers else _spoken_percent(value)
        if percent is None:return {'error':'قول النسبة اللي عايزها، زي خمسة وتلاتين في المية.'}
        if not 0<=percent<=100:return {'error':'النسبة لازم تكون من صفر لمية.'}
        return {'setting':setting,'action':'set','percent':percent}
    step=int(numbers[0]) if numbers else _spoken_percent(value)
    if step is None:step=10
    if not 1<=step<=25:return {'error':'مقدار الزيادة أو النقص يكون من 1 إلى 25. لو عايز مستوى محدد قول ظبط الصوت على النسبة.'}
    return {'setting':setting,'action':'down' if down else 'up','percent':step}


_NUMBERS = {
    'صفر':0, 'واحد':1, 'اتنين':2, 'اثنين':2, 'تلاته':3, 'ثلاثه':3, 'اربعه':4,
    'خمسه':5, 'سته':6, 'سبعه':7, 'تمانيه':8, 'ثمانيه':8, 'تسعه':9, 'عشره':10,
    'عشرين':20, 'تلاتين':30, 'ثلاثين':30, 'اربعين':40, 'خمسين':50,
    'ستين':60, 'سبعين':70, 'تمانين':80, 'ثمانين':80, 'تسعين':90,
    'ميه':100, 'مائه':100, 'مية':100,
}


def _spoken_percent(value: str) -> int | None:
    value = re.sub(r' (?:في الميه|في المية|بالمية|بالمئه|بالمئة|بالمائه)$', '', value)
    words = value.replace('ة','ه').split()
    if not words:
        return None
    if words[-1] in ('النص','نص'):
        return 50
    tens = _NUMBERS.get(words[-1], _NUMBERS.get(words[-1].removeprefix('و')))
    if tens is None:
        return None
    if len(words) >= 2 and 20 <= tens < 100:
        unit = _NUMBERS.get(words[-2] if words[-2] != 'و' else (words[-3] if len(words) >= 3 else ''))
        if unit is not None and 1 <= unit <= 9:
            return unit + tens
    return tens
