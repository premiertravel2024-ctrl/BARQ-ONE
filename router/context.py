"""Deterministic, no-extra-API-call context selection for long conversations.

Never summarize text we haven't read or pretend an omitted message was sent.
Always keep system instructions and the last user message; use relevance to
retain helpful older turns when a model has a small context window.
"""
import re


def _size(message):
    return len(str(message.get('content', ''))) + 32


def _terms(message):
    text = str(message.get('content', '')).lower()
    # Normalize frequent colloquial Arabic spelling while keeping this local,
    # deterministic and dependency-free. Token extraction is retrieval only.
    text = text.replace('أ','ا').replace('إ','ا').replace('آ','ا').replace('ى','ي')
    return set(re.findall(r'[\w.-]{3,}', text))


def select_context(messages, context_window=8192):
    """Return (selected messages, omitted count) within a conservative size budget.

    An oversize final prompt is kept intact: downstream model might reject it,
    but silently truncating the user's latest explicit request is worse.
    """
    if not messages:
        return [], 0
    cap = max(4000, int(context_window * 2.0))
    if sum(_size(m) for m in messages) <= cap:
        return messages, 0
    selected = set(i for i, m in enumerate(messages) if m.get('role') == 'system')
    selected.add(len(messages) - 1)
    used = sum(_size(messages[i]) for i in selected)
    # Recent exchanges take precedence over older lexical matches.
    for i in range(len(messages)-2, max(-1, len(messages)-9), -1):
        if i not in selected and used + _size(messages[i]) <= cap * .68:
            selected.add(i)
            used += _size(messages[i])
    wanted = _terms(messages[-1])
    # Real tool outcomes, tests and current task progress are more valuable
    # than repeated prose; preserve them across model handoffs when possible.
    evidence = re.compile(r'\b(?:test|pytest|failed|passed|tool|checkpoint|sha256|error|exit_code)\b|(?:اختبار|نتيجة|خطأ|اتحفظ|اتنفذ|الملف)',re.I)
    earlier = sorted((i for i in range(len(messages)) if i not in selected),
                     key=lambda i: (len(_terms(messages[i]) & wanted)*5 +
                                    (3 if evidence.search(str(messages[i].get('content',''))[:1200]) else 0),i),reverse=True)
    for i in earlier:
        if used + _size(messages[i]) <= cap:
            selected.add(i)
            used += _size(messages[i])
    # Keep a tool result with its initiating assistant action where feasible;
    # never move or fabricate a response. Remove the orphaned result if its
    # matching call cannot fit rather than showing unauthenticated evidence.
    for i in list(selected):
        if messages[i].get('role') == 'tool' and i > 0 and i-1 not in selected:
            if used + _size(messages[i-1]) <= cap:
                selected.add(i-1); used += _size(messages[i-1])
            else:
                selected.remove(i)
    return [messages[i] for i in sorted(selected)], len(messages) - len(selected)


def effective_window(provider, model):
    """Ollama's configured native num_ctx is the *actual* local limit."""
    if provider.kind == 'local':
        from providers.streaming import _ollama_settings
        num_ctx, _ = _ollama_settings(model)
        return min(model.context_window, num_ctx)
    return model.context_window
