"""Bounded, unambiguous JSON extraction from free-model completions."""
import json
import re


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def model_object(content):
    if not isinstance(content, str) or len(content.encode('utf-8')) > 256000:
        raise ValueError('Invalid or oversized model response')
    clean = content.strip().lstrip('\ufeff')
    # Markdown fences are presentation, not a second JSON document.
    if clean.startswith('```'):
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', clean, flags=re.I).strip()
    decoder = json.JSONDecoder(object_pairs_hook=_unique)
    try:
        value = decoder.decode(clean)
    except json.JSONDecodeError:
        # An LLM may prefix a JSON object with a brief explanation. Scan only
        # outside quoted strings, never silently select among two objects.
        # Prefer the outermost decodable object. Nested objects are part of
        # that contract, not competing completions.
        found = None
        for pos, char in enumerate(clean):
            if char != '{':
                continue
            try:
                candidate, consumed = decoder.raw_decode(clean[pos:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                found = (pos, pos + consumed, candidate)
                break
        if found is None:
            raise ValueError('No JSON object')
        start, end, value = found
        before, after = clean[:start], clean[end:]
        # Trailing prose / closing markdown fences are okay, but another
        # JSON value or unbalanced JSON-looking text is never acceptable.
        if re.search(r'[{}\[\]]', before + after):
            raise ValueError('Ambiguous multiple JSON documents')
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value
