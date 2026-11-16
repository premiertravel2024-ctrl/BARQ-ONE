"""A deliberately narrow bridge from user chat to *real* local integrations.

Only the user's directly typed message is inspected. The classifier never reads
model output, retrieved pages, tool results or attachment content. Detection is
read-only: it does not start a process or execute a tool.
"""
import re
from mcp.bridge import SERVERS, available
from agent.intent_patterns import mentions_rea_request

_REA = re.compile(r'(?<![\w])rea(?![\w])|(?<![\w])ريا(?![\w])', re.IGNORECASE)
_ACTION = re.compile(r'(?:\b(?:run|execute|analy[sz]e|inspect|open|use|scan|reverse.engineer|start)\b|'
                     r'حل[ّلاي]|حلل|شغ[ّغ]?ل|استخدم|افتح|افحص|نف[ّذ]|ابد[اأ]|اعمل\s+تحليل|'
                     r'حلل[يه]ا|استخدم[يه]ا)', re.IGNORECASE)
_CONDITIONAL = re.compile(r'(?:\b(?:can|could|would|if|possible|able to|do you)\b|'
                          r'تقدر|ينفع|ممكن|هل|لو\s+بع[تث]|لو\s+بعت)', re.IGNORECASE)


def classify_direct_user_text(text: str) -> dict | None:
    """Surface REA to the user without pretending it has been invoked."""
    if not isinstance(text, str) or not mentions_rea_request(text):
        return None
    clean = text[:4000].strip()
    # Capability questions about REA are NOT permission to execute it.
    capability = bool(_CONDITIONAL.search(clean))
    action = bool(_ACTION.search(clean)) and not capability
    server = SERVERS.get('rea')
    installed = bool(server and available(server))
    enabled = bool(server and server.enabled)
    if not installed:
        status = 'runner_missing'
    elif not enabled:
        status = 'disabled'
    else:
        status = 'not_tested'
    return {
        'integration': 'rea',
        'intent': 'request' if action else 'capability',
        'status': status,
        'runner_available': installed,
        'enabled': enabled,
        'connected': False,  # Only tools/list may establish a live MCP connection.
        'requires_approval': True,
        'message_ar': (
            'أيوه، ابعت مسار البرنامج أو اختار مجلد المشروع عشان أجهّز التحليل بأداة REA.'
            if not action else
            'اختار مجلد المشروع وافحص اتصال REA لبدء تجهيز التحليل.'
        ),
        'message_en': (
            'BARQ can use REA through its MCP integration once connected. Select a project and '
            'discover the tools first. No REA action has run yet.'
            if not action else
            'BARQ recognized your REA request. Select a project in Coding Workspace and '
            'discover the available REA tools; each execution requires approval.'
        ),
    }


def integration_reply(messages):
    """Plain API/legacy clients also get truthful local capability handling.

    A capability reply does not discover or run any tool.
    """
    last = next((m for m in reversed(messages) if m.get('role') == 'user'), None)
    if not last:
        return None
    text = last.get('content', '')
    request = classify_direct_user_text(text)
    if not request:
        return None
    return request['message_ar'] if re.search(r'[\u0600-\u06ff]', text) else request['message_en']
