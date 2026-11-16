"""Best-effort credential masking before passing repository text to a cloud LLM.

This is not a DLP guarantee. The workspace owner decides which code may be
sent to remote models; the local-only Ollama mode avoids that transfer.
"""
import re

_CREDENTIAL_KEYS = r'(?:[A-Z_]*?(?:API[_-]?KEY|ACCESS[_-]?TOKEN|SECRET|PASSWORD|PRIVATE[_-]?KEY|AUTH[_-]?TOKEN)[A-Z_]*)'
_ASSIGN = re.compile(
    r'(?i)(?P<prefix>[\"\']?' + _CREDENTIAL_KEYS + r'[\"\']?\s*[:=]\s*)'
    r'(?P<quote>[\"\']?)(?P<value>[^\"\'\s,#;]+)',
)
_INLINE = re.compile(
    r'\b(?:sk-[A-Za-z0-9_-]{18,}|AIza[A-Za-z0-9_-]{25,}|'
    r'gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'
)
_BEARER = re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}')
_PRIVATE_BLOCK = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----')


def redact(text: str) -> str:
    text = _PRIVATE_BLOCK.sub('[REDACTED PRIVATE KEY]', text)
    text = _ASSIGN.sub(lambda m: m.group('prefix') + m.group('quote') + '[REDACTED]', text)
    text = _INLINE.sub('[REDACTED TOKEN]', text)
    return _BEARER.sub('Bearer [REDACTED]', text)
