"""Classify directly typed task intent before chat streaming. Read-only and conservative.

This module NEVER runs commands or trusts document, model, or tool content.
"""
import re
from agent.intent_patterns import mentions_rea_request

CAPABILITY = re.compile(r"^(?:(?:can you|could you|are you able|do you support|is it possible)\b|(?:هل|هو|تقدر|بتعرف|ينفع)\s+|ممكن\s+(?:تقولي|تشرح|توضح|اعرف)|لو\s+(?:بعتلك|بعثتلك|عندي))",re.I)
REA = re.compile(r"(?<![a-z0-9_])rea(?![a-z0-9_])|(?<![\w])ريا(?![\w])",re.I)
ACTION = re.compile(r"(?:\b(?:run|execute|open|close|copy|move|delete|rename|click|scroll|switch|create|edit|modify|fix|repair|build|test|scan|analy[sz]e|rename|write|save|install|launch|delete)\b|(?:افتح|اقفل|قفل|انسخ|انقل|الصق|احذف|اضغط|دوس|بدل|شغل|شغّل|حلل|حلّل|افحص|عدل|عدّل|صلح|أصلح|دوّر|دورلي|دور|ابحثلي|هاتلي|جيبلي|شوفلي|نفذ|نفّذ|ابني|ابن[يِ]|برمج|برمجي|اصنع|صمم|صمّم|اعمل|أنشئ|انشئ|اكتب|اختبر|اختبار|غيّر|غير|احفظ|رتب|سم[ّ]?ي|امسح))",re.I)
CODE = re.compile(r"(?:\b(?:code|repository|project|repo|python|typescript|javascript|github|pytest|tests|unit tests|exe|source|build|react|git)\b|(?:كود|الكود|ملف|ملفات|مشروع|المشروع|برنامج|البرنامج|سورس|اكواد|أكواد|اختبارات|الاختبارات|برمجة|تطبيق|تطبيقات|مستودع|واجهة|موقع|الموقع|ويب))",re.I)
DESKTOP_APP = re.compile(r"(?:\b(?:notepad|excel|word|browser|calculator|powerpoint|chrome|edge)\b|(?:المفكرة|النوتباد|الاكسيل|اكسيل|اكسل|إكسل|وورد|بوربوينت|باوربوينت|كروم|المتصفح|سطح المكتب))", re.I)
COMPUTER = re.compile(r"(?:\b(?:notepad|excel|word|browser|desktop|file explorer|calculator|powerpoint|chrome|edge|computer|pc|windows)\b|(?:المفكرة|النوتباد|الاكسيل|اكسيل|اكسل|إكسل|وورد|بوربوينت|باوربوينت|كروم|المتصفح|سطح المكتب|مجلد التنزيلات|الملفات على الجهاز|على الجهاز|في الجهاز|الكمبيوتر|المعالج|كارت الشاشة|البطارية|أفلام الجهاز))",re.I)


BUILD_VERB = re.compile(r"(?:ابني(?:لي|ليّ|\s+لي)?|تبني(?:لي|\s+لي)?|تعمل(?:لي|ليّ|\s+لي|ه)?|اعمل(?:لي|\s+لي)?|اعملي|أنشئ(?:لي|\s+لي)?|انشئ(?:لي|\s+لي)?|اصنع(?:لي|\s+لي)?|برمج(?:لي|\s+لي)?|صمم(?:لي|\s+لي)?|جهز(?:لي|\s+لي)?|create|build|make|develop)",re.I)
APP_NOUN = re.compile(r"(?:برنامج|تطبيق|مشروع|موقع|سيستم|سكريبت|سكربت|script|app(?:lication)?|software|website|web\s+app|desktop\s+app|tool)",re.I)
NOT_BUILD = re.compile(r"(?:مقارنة|شرح|مثال|فكرة\s+عن|وصف|تصور|برومبت|اشرح|compare|explain|example|prompt)",re.I)

def asks_to_build_application(value: str) -> bool:
    """The requested object governs intent, not a later 'do not just explain' rule."""
    head=primary_request(value)
    build=BUILD_VERB.search(head)
    noun=APP_NOUN.search(head,build.end()) if build else None
    if not build or not noun:return False
    # 'write a prompt/example about building an app' is content, whereas
    # 'build an app, do not just explain' is an actionable project request.
    return not bool(NOT_BUILD.search(head[:noun.start()]))


def primary_request(value: str) -> str:
    """Inspect the leading user request without discarding its full requirements."""
    from core.addressing import normalized
    head=re.split(r'\n|[.!؟?](?:\s|$)',value.strip(),maxsplit=1)[0]
    head=normalized(head)
    return re.sub(r'^(?:(?:يا\s+)?(?:برق|barq)(?:\s*ai)?\s*[،,:؛!]?\s*)','',head,flags=re.I).strip()

FOLLOW_UP = re.compile(r'^(?:كمل|كمّل|كمل\s+المشروع|كمّل\s+المشروع|صلح\s+الخطأ|صلّح\s+الخطأ|كملها|كمّلها|اعمله|اعملها|عاوزك\s+تعمله|انا\s+عاوزك\s+تعمله|ابدأ|اشتغل عليه|نفذ|نفّذ|نفذه|نفّذه|حلله|حلّله|افحصه|صلحه|صلّحه|حاول(?:\s+تاني)?|جرّ?ب(?:\s+تاني)?|continue|retry|proceed|do it|analyze it|inspect it|fix it)[.!؟?\s]*$', re.I)


def classify_task(text: str, previous_user_texts=None) -> dict | None:
    """Only explicitly requested desktop/project actions become agent tasks.

    A capability question or a generic request to *write code in chat* is not
    permission to modify source or operate the desktop.
    """
    if not isinstance(text,str):return None
    value=text.strip()[:12000]
    if FOLLOW_UP.fullmatch(value):
        # Only directly typed user turns can supply the target.
        for previous in reversed((previous_user_texts or [])[-8:]):
            if not isinstance(previous,str) or FOLLOW_UP.fullmatch(previous.strip()):continue
            earlier=classify_task(previous)
            if earlier:
                return {**earlier,'goal':earlier['goal']+'\nمتابعة المستخدم: '+value,'contextual':True}
            if mentions_rea_request(previous):
                return {'kind':'rea','goal':previous+'\nمتابعة المستخدم: '+value,'requires_approval':True,'contextual':True}
            # A different recent topic must not revive an obsolete task.
            break
        return None
    head=primary_request(value)
    if not value or CAPABILITY.search(head):return None
    if re.match(r"^(?:لا\s+(?:تبني|تنفذ|تعمل|تغير|تعدل|تمسح|تفتح|تشغل)|(?:ما\s+|مت)(?:عمل|تعمل|غير|تغير|عدل|تعدل|مسح|تمسح|نفذ|تنفذ|فتح|تفتح|شغل|تشغل)[^\s]*ش|مش\s+(?:عاوزك|عايزك|محتاجك)|do\s+not\b|don't\b)",head,re.I):
        return None
    if re.match(r"^(?:ترجم|لخص|اشرح|اشرحلي|ازاي|كيف|how\b|explain\b|translate\b|summarize\b|اكتب(?:لي)?\s+(?:برومبت|مثال|وصف|رسالة)|write\s+(?:a\s+)?(?:prompt|example|description))",head,re.I) and not re.search(r"(?:نفذ|نفّذ|ابدأ\s+تنفيذ|و?طبّق|و?طبق|then\s+(?:build|execute|create))",head,re.I):
        return None
    from computer_control.tools.direct_intent import direct_action
    from computer_control.tools.direct_sequence import direct_sequence
    if direct_action(value) or direct_sequence(value):
        return {'kind':'computer','goal':value,'requires_approval':True}
    building_app=asks_to_build_application(value)
    if not building_app and not ACTION.search(value):return None
    if not building_app and re.match(r'^(?:اقفل|قفل|انسخ|انقل|الصق|احذف|امسح|اضغط|دوس|بدل|close|copy|move|delete|rename|click|scroll|switch)\b',head,re.I):
        return {'kind':'computer','goal':value,'requires_approval':True}
    if mentions_rea_request(value):return {'kind':'rea','goal':value,'requires_approval':True}
    if not building_app and re.match(r'^(?:افتح(?:لي|ي|ه)?|تفتح(?:لي)?|شغل(?:لي|ي|ه)?|open|launch|start)\b',head,re.I) and not re.search(r'(?:اختبارات|الاختبارات|\btests?\b|\bpytest\b|سورس|كود|\bcode\b|\.(?:py|ts|tsx|js|jsx|rs)\b)',head,re.I):
        return {'kind':'computer','goal':value,'requires_approval':True}
    if not building_app and (DESKTOP_APP.search(value) or (COMPUTER.search(value) and not CODE.search(value))):
        return {'kind':'computer','goal':value,'requires_approval':True}
    if CODE.search(value) or building_app:
        existing_build=bool(re.search(r'(?:من|لل|في|داخل)\s*(?:ال)?مشروع|existing\s+project|from\s+(?:the\s+)?project',value,re.I))
        new_project=building_app and not existing_build
        # 'اكتب كود Python' is a normal chat content request unless a local
        # project/file or execution is clearly requested.
        just_write=re.search(r"(?:اكتبلي|اكتب|write|اشرح|explain)\s+(?:لي\s+)?(?:كود|code|برنامج|python)",value,re.I)
        actual_work=re.search(r"(?:مشروع|المشروع|ملف|ملفات|سورس|مستودع|repository|repo|\bbuild\b|\bexe\b|\btests?\b|اختبارات|الاختبارات|على جهازي|داخل|في المشروع)",value,re.I)
        if just_write and not actual_work and not new_project and not re.search(r'برنامج|تطبيق|application|app',value,re.I):return None
        # Requests to compose, describe or compare code are chat answers, not
        # authorization to execute or change an existing project.
        if not actual_work and re.search(r'(?:اعمل\s+(?:مقارنة|شرح|مثال|كود)|(?:انشئ|أنشئ|اكتب|write|create)\s+(?:لي\s+)?(?:مثال|كود|code)|explain|compare)',value,re.I):
            return None
        return {'kind':'coding','goal':value,'requires_approval':True,'new_project':new_project}
    if COMPUTER.search(value):return {'kind':'computer','goal':value,'requires_approval':True}
    return None
