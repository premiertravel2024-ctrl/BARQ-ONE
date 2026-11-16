"""Recognize simple direct Office requests before filename matching."""
import re
from .nlu import clean,FILLERS

LABELS={'excel':'Excel','word':'Word','powerpoint':'PowerPoint'}
FORMS={'excel':{'اكسل','اكسيل','الاكسل','الاكسيل','اكسلسل','excel'},
       'word':{'وورد','الوورد','ورد','word'},
       'powerpoint':{'باوربوينت','الباوربوينت','بوربوينت','powerpoint'}}
DOCS={'شيت','sheet','spreadsheet','workbook','مصنف','جدول','مستند','document','doc','عرض','presentation','صفحه','ملف','file'}
NEW={'جديد','جديده','فاضي','فاضيه','فارغ','فارغه','blank','new'}
FILL={'لي','a','an','the','واحد','واحده','بتاع','برنامج','تطبيق','app','application','مايكروسوفت','microsoft'}


def office_request(text:str)->dict|None:
    value=clean(text)
    value=re.sub(r'^(?:(?:'+FILLERS+r')(?:\s+|$))+','',value).strip()
    verb=re.match(r'^(افتح(?:لي|ي|هالي|هولي)?|فتحلي|شغل(?:لي|ي)?|تفتح(?:لي)?|تشغل(?:لي)?|اعمل(?:لي|ي)?|انشئ(?:لي)?|جهز(?:لي)?|open|launch|start|create|make)\s+',value)
    if not verb:return None
    words=value[verb.end():].split()
    apps=[key for key,forms in FORMS.items() if set(words)&forms]
    if not apps and set(words)&{'شيت','sheet','spreadsheet','workbook','مصنف'}:apps=['excel']
    if len(apps)!=1:return None
    app=apps[0]
    permitted=FORMS[app]|DOCS|NEW|FILL
    # A filename, destination, table contents or additional action belongs to
    # the existing file resolver/planner; never silently discard requirements.
    if not words or any(word not in permitted for word in words):return None
    creating=bool(set(words)&(NEW|DOCS)) or verb.group(1).startswith(('اعمل','انشئ','جهز','create','make'))
    return {'app':app,'action':'new' if creating else 'open'}
