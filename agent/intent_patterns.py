"""Recognize direct user requests; never inspect documents or tool output here."""
import re


def normalize(text):
    value = re.sub(r'[\u064b-\u065f\u0670\u0640]', '', text[:12000]).lower()
    return value.translate(str.maketrans({'أ':'ا', 'إ':'ا', 'آ':'ا', 'ى':'ي', 'ة':'ه'}))


def mentions_rea_request(text):
    value = normalize(text)
    if re.search(r'(?<![\w])(?:rea|ريا)(?![\w])', value):
        return True
    reverse = re.search(r'هندس[ه]?\s+(?:ال)?عكسي[ه]?|\breverse[ -]engineer(?:ing)?\b', value)
    if not reverse:
        return False
    # Definitions and educational explanations stay ordinary chat. A request
    # to inspect an app, including a capability question, uses the integration.
    action = re.search(r'حلل|حللي|تحلل|تحليل|افحص|استخدم|نفذ|\b(?:analy[sz]e|inspect|use|run)\b', value)
    target = re.search(r'برنامج|تطبيق|مشروع|ملف|\b(?:app|program|binary|exe|dll|project|file)\b', value)
    question = re.search(r'تقدر|ممكن|ينفع|\b(?:can you|could you|able to)\b', value)
    return bool(action or (question and target))
