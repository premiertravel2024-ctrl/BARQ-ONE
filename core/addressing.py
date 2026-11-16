"""Product-name addressing and per-turn language expectations; no provider calls."""
import re
import unicodedata

_NAME=r'(?:برق(?:\s*(?:ai|اي\s*اي))?|barq(?:\s*ai)?)'
_CALL=re.compile(r'^(?:(?:يا|hey|hi|hello)\s+)?'+_NAME+r'[\s!！؟?.,،:؛…]*$',re.I)
_PREFIX=re.compile(r'^(?:يا\s+)?'+_NAME+r'(?:\s*[،,:!؟?]\s*|\s+)(.+)$',re.I)
_ACTION=re.compile(r'^(?:كمل|كمّل|ظبط|ظبّط|زبط|افتح|شغل|شغّل|نفذ|نفّذ|احفظ|صلح|صلّح|عدل|عدّل|راجع|حلل|حلّل|حلله|افحص|ابني|اكتب|ترجم|لخص|ضيف|شيل|وقف|اقفل|continue\b|open\b|run\b|fix\b|save\b|review\b)',re.I)
_TARGET=r'(?:ال)?(?:انجليزي[هة]?|إنجليزي[هة]?|فارسي[هة]?|فرنسي[هة]?|ياباني[هة]?|الماني[هة]?|ألماني[هة]?|اسباني[هة]?|إسباني[هة]?|صيني[هة]?|كوري[هة]?|تركي[هة]?|روسي[هة]?|انجليش|english)'
_FOREIGN=re.compile(r'(?:(?:^|\s)(?:رد|جاوب|اتكلم|كلمني|قولها|اكتب|خلي\s+الرد).{0,35}(?:بال|لل|إلى\s*|الى\s*)'+_TARGET+r'|(?:ترجم|ترجمة).{0,100}'+_TARGET+r'|(?:reply|answer|respond|translate|write|speak).{0,60}\b(?:in|into|to)\s+(?:english|persian|farsi|french|german|japanese|spanish|chinese))',re.I)
_FOREIGN_ONLY=re.compile(r'^(?:بال|ب)'+_TARGET+r'[.!؟?\s]*$',re.I)
_EGYPTIAN_REQUEST=re.compile(r'(?:اتكلم|كلمني|رد|جاوب).{0,15}(?:مصري|بالعربي)',re.I)
_PERSIAN_WORDS=re.compile(r'(?<!\w)(?:شما|لطفاً|لطفا|منظورتان|منظور|کاربردهای|می\s*توانم|می\s*توانید|می‌توانم|می‌توانید|کمکتان|چگونه|برای|است|دارند|کدام|نیروی|بیشتر|مشخص)(?!\w)')


def normalized(text):
    text=unicodedata.normalize('NFKC',str(text)).strip().lower()
    return re.sub(r'[\u064b-\u065f\u0670\u0640]','',text)


def address_reply(text):
    value=normalized(text)
    if not _CALL.fullmatch(value):return None
    return 'أيوه، معاك. قولّي.' if re.search(r'[\u0600-\u06ff]',value) else "I'm here. What do you need?"


def casual_greeting_reply(text):
    """A small, safe set of direct greetings; never swallow commands or questions.

    Models with tiny local contexts sometimes copy a greeting verbatim instead
    of replying. Handle only an entire recognized greeting (not a substring).
    """
    value=normalized(text).translate(str.maketrans({"إ":"ا","أ":"ا","آ":"ا"}))
    value=re.sub(r'[!！؟?.,،:؛…]+', ' ', value)
    value=re.sub(r'\s+', ' ', value).strip()
    value=re.sub(r'\bيا(?=عم\b|برق\b|صاحبي\b)', 'يا ', value)
    # A direct check-in, optionally calling BARQ by name. No action words or
    # additional clauses can match the full expression.
    if (re.fullmatch(r'(?:ازيك|ازيّك|عامل ايه|عامل اية|اخبارك|ايه الاخبار|ايه اخبارك)(?: يا)?(?: عم| صاحبي)?(?: يا)?(?: عم)?(?: برق(?: ai| اي اي)?| barq(?: ai)?)', value)
        or re.fullmatch(r'(?:صباح الخير|مسا الخير|مساء الخير)(?: يا)?(?: عم| صاحبي)?(?: يا)?(?: برق(?: ai| اي اي)?| barq(?: ai)?)?', value)):
        if value.startswith('صباح الخير'):
            return 'صباح الفل يا صاحبي! عامل إيه النهارده؟'
        if value.startswith(('مسا الخير', 'مساء الخير')):
            return 'مسا الفل يا صاحبي! أخبارك إيه؟'
        return 'الحمد لله يا صاحبي، إنت عامل إيه؟'
    if value in ('السلام عليكم','سلام عليكم'):
        return 'وعليكم السلام يا صاحبي! عامل إيه؟'
    return None

def command_without_address(text):
    # Only remove the name prefix; paths and case-sensitive symbols must remain exact.
    value=str(text).strip()
    match=_PREFIX.fullmatch(value)
    return match.group(1) if match and _ACTION.search(match.group(1)) else text


def expects_egyptian(messages):
    last=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')
    arabic=bool(re.search(r'[\u0600-\u06ff]',last))
    if _EGYPTIAN_REQUEST.search(last) and not re.search(r'ترجم|translate',last,re.I):return arabic
    return arabic and not (_FOREIGN.search(last) or _FOREIGN_ONLY.fullmatch(last.strip()))


def persian_drift(text):
    # Examine prose only, preserving code, quoted examples and translations.
    prose=re.sub(r'```[\s\S]*?```|`[^`]*`','',text)
    words=set(_PERSIAN_WORDS.findall(prose))
    return len(words)>=3 or (len(words)>=2 and bool(re.search(r'[گچپژی]',prose)))
