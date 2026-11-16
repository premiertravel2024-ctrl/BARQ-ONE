"""Guard against a past React build blocker: `decision` used before declaration.

Full npm/TypeScript build remains the authoritative check. This small test is
an inexpensive regression sentinel in the Python suite too.
"""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
CHAT=ROOT/'frontend/src/lib/chat.ts'


def test_local_action_decision_is_declared_before_first_use():
    content=CHAT.read_text(encoding='utf-8')
    # A typed local binding must exist inside generate()'s user action handling.
    binding=re.search(r'\b(?:let|const)\s+decision\s*:\s*Decision\s*=\s*\{\s*intent\s*:\s*null\s*\}', content)
    assert binding, 'chat.ts needs a scoped, typed `decision` binding before action routing.'
    references=[m.start() for m in re.finditer(r'\bdecision\b', content)]
    # Ignore the name in incidental comments, check the first runtime reference.
    runtime=re.search(r'(?<!\.)\b(?:decision\.intent|decision\.clarification|decision\.reply|decision\s*=)',content)
    assert runtime and binding.start()<runtime.start(), 'Decision must be declared before it is used.'
    assert len(references)>2


def test_decision_is_created_even_for_non_action_chat():
    content=CHAT.read_text(encoding='utf-8')
    assert re.search(r'let\s+decision:Decision\s*=\s*\{intent:null\};',content)
    assert 'if(actionLike)' not in content, 'Unknown wording must reach understanding as well.'
