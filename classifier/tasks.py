import re
KEYWORDS = {
 'coding': ['صلحلي','صلح','كمل المشروع','اعمل برنامج','ابنيلي','ابني','اختبرلي','نفذ التعديل','ظبط السورس','code','python','javascript','debug','program','كود','برمجة','خطأ برمجي','repo','repository','typescript','rust','git','refactor','fix bug','اختبار','تصليح','اصلاح','برمج','مشروع','github','github actions','exe'],
 'reasoning': ['حلللي','قارنلي','فهمني','فكر','خطط','prove','reason','math','equation','برهان','معادلة','احسب'],
 'translation': ['translate','translation','ترجم','ترجمة'],
 'summarization': ['summarize','summary','لخص','تلخيص'],
 'vision': ['image','picture','photo','صورة','الصورة'],
 'writing': ['write','draft','email','اكتب','صياغة','رسالة'],
 'long-document': ['document','report','pdf','مستند','تقرير'],
}
def classify(messages):
    # Classify the current request; an older coding task must not turn a new joke into a coding request.
    s=next((str(m.get('content','')) for m in reversed(messages) if m.get('role')=='user'),'')[-30000:].lower()
    scores={k:sum(1 for word in words if word in s) for k,words in KEYWORDS.items()}
    task=max(scores,key=scores.get) if max(scores.values(),default=0)>0 else 'simple'
    if scores['coding'] and scores['coding'] >= max(scores.values()):task='coding'
    if re.search(r'[\u0600-\u06ff]',s) and task=='simple': task='arabic'
    difficulty='hard' if len(s)>9000 or any(x in s for x in ('complex','architecture','معقد','تصميم نظام')) else 'medium' if len(s)>1000 else 'easy'
    return task,difficulty
