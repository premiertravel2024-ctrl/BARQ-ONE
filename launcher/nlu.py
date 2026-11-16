"""Egyptian / MSA / Franco / English launch intent classification. No IO."""
from __future__ import annotations
from dataclasses import dataclass
import re
from agent.intent_patterns import normalize as arabic_normalize

@dataclass(frozen=True)
class LaunchIntent:
    verb: str
    target_text: str
    target_kind: str | None = None
    ext_hints: tuple[str, ...] = ()
    recency_hint: str | None = None
    confidence: float = 1.0

FILLERS = r'(?:يا\s+برق|يا\s+barq|لو\s+سمحت|من\s+فضلك|ممكن|بالله\s+عليك|بقا|كده|كدا|يا\s+معلم|يا\s+باشا|please|hey\s+barq)'
VERBS = [
    (r'(?:افتح(?:لي|هالي|هولي|ه)?|تفتح(?:لي)?|فتحلي|شغل(?:لي|هالي|ه)?|تشغل(?:لي)?|وريني|هاتلي|(?:عايز|عاوز)(?:ك)?\s+(?:افتح|تفتح|تشغل)|نفسي\s+افتح|روح\s+ل|روح\s+علي|ارجع\s+ل|open|launch|start|run|show\s+me|3ayez\s+aft[aeh]7|efta7|efta7li|eshaghal|shaghal)', 'open'),
    (r'(?:صغر|قلل|mini?mize)', 'minimize'),
    (r'(?:كبر|maximi[sz]e)', 'maximize'),
    (r'(?:اقفل|سكر|close|exit)', 'close'),
]
EXT = {'pdf':('.pdf',),'اكسل':('.xlsx','.xls','.csv'),'excel':('.xlsx','.xls','.csv'),
       'وورد':('.docx','.doc'),'word':('.docx','.doc'),'صوره':('.png','.jpg','.jpeg','.webp'),
       'فيديو':('.mp4','.mov','.mkv'),'اغنيه':('.mp3','.wav')}
KIND = {'ملف':'file','فايل':'file','file':'file','folder':'folder','فولدر':'folder','مجلد':'folder',
        'برنامج':'app','تطبيق':'app','app':'app','application':'app',
        'موقع':'site','صفحه':'site','لينك':'site','website':'site','site':'site'}
QUESTION = re.compile(r'^(?:هو\s+|هل\s+|ينفع\s+|تقدر\s+|بتعرف\s+|ازاي\s+|ايه\s+|what\s+|can\s+you\b|could\s+you\b|how\s+to\b|do\s+you\b)')

def clean(text: str) -> str:
    value = arabic_normalize(str(text or '').strip()[:600]).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789'))
    value = re.sub(r'(.)\1{3,}',r'\1\1',value)
    return re.sub(r'\s+',' ', re.sub(r'[؟?!،,]+',' ',value)).strip()

def parse(text: str) -> LaunchIntent | None:
    from voice.intent import command_target, command_text, non_executable

    if not isinstance(text, str) or len(text.strip()) > 240 or non_executable(text):
        return None
    canonical = command_text(text).split(maxsplit=1)
    if len(canonical) == 2 and canonical[0] in ('افتح', 'شغل'):
        text = f'{canonical[0]} {command_target(text)}'
    normalized=clean(text)
    if not normalized or QUESTION.match(normalized):return None
    # Capability questions that were not expressed as a direct launch.
    if re.search(r'^(?:ممكن تقولي|هل يمكنك)\b', normalized):
        return None
    normalized=re.sub(r'^(?:(?:'+FILLERS+r')(?:\s+|$))+','',normalized).strip()
    normalized=re.sub(r'\s+(?:(?:'+FILLERS+r'|بقى|النهارده دلوقتي|دلوقتي)(?:\s+|$))+$','',normalized).strip()
    verb=None
    for pattern,action in VERBS:
        m=re.match(r'^(?:'+pattern+r')(?:\s+|$)',normalized)
        if m:verb=action;normalized=normalized[m.end():].strip();break
    if verb is None:return None
    literal=re.search(r'(?:https?://|[A-Za-z]:[\\/]|/)[^\r\n]*$',str(text).strip())
    if verb=='open' and literal:
        target=literal.group(0).strip().rstrip('\"\'')
        if target.startswith(('http://','https://')) or re.match(r'^(?:[A-Za-z]:[\\/]|/)',target):
            return LaunchIntent(verb,target,'site' if target.startswith(('http://','https://')) else None)

    normalized=re.sub(r'^(?:لي|لي\s+|ال|the\s+)(?=\s|$)','',normalized).strip()
    if normalized.startswith('لي '):normalized=normalized[3:]
    if not normalized:return None
    hint=None
    prefix=re.match(r'^(ملف|فايل|file|folder|فولدر|مجلد|برنامج|تطبيق|app|application|موقع|صفحه|لينك|website|site)\s+',normalized)
    if prefix:hint=KIND[prefix.group(1)];normalized=normalized[prefix.end():]
    ext=tuple(e for key,extensions in EXT.items() if key in normalized.split() for e in extensions)
    recency=None
    for label,terms in {'latest':['اخر','احدث','latest','last'],'today':['النهارده','النهارد','today'],
                        'yesterday':['امبارح','yesterday'],'week':['الاسبوع ده','this week']}.items():
        if any(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',normalized) for term in terms):
            recency=label
            for term in terms:normalized=re.sub(r'(?<!\w)'+re.escape(term)+r'(?!\w)',' ',normalized)
            break
    normalized=re.sub(r'\s+',' ',normalized).strip(' .')
    if not normalized or normalized in ('حاجه','شيء','anything'):return None
    if hint is None and re.search(r'(?i)\.(?:pdf|xlsx?|docx?|pptx?|txt|csv|png|jpe?g|zip|rar|7z|mp4|mkv)$',normalized):hint='file'
    return LaunchIntent(verb,normalized,hint,ext,recency,.98)
