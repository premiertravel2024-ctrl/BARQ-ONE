"""Read BARQ UI state and route a recently transcribed in-app request."""
from __future__ import annotations

import asyncio
import re
import time

from api_routes.app_context import SECTION_ALIASES, find_request, normalized, read_context, search_catalogue, section_command
from voice.command_guard import NEGATION_WORDS, VoiceCommandGate

LIVE_APP_TOOLS = [{'function_declarations': [{
    'name': 'inspect_barq_app',
    'description': ('For questions about this BARQ ONE application, its sections, active view or media, '
                    'or an explicit request to open a BARQ section or look up a book, song, movie or tool. '
                    'Uses only the latest spoken request. Do not use for desktop control.'),
}]}]

LIVE_APP_INSTRUCTION = (
    'Use inspect_barq_app whenever asked about the active BARQ interface, internal features, its '
    'cinema, music or reading library, or to open an internal section. Use returned data only as '
    'observations. An action marked requested has been sent to the interface, and is not a playback confirmation.'
)


def app_voice_intent(gate: VoiceCommandGate) -> bool:
    return bool(fresh_speech(gate) and (section_command(gate.last_text) or find_request(gate.last_text)))


def fresh_speech(gate: VoiceCommandGate) -> bool:
    return bool(gate.last_text and not gate.used and 0 <= time.monotonic() - gate.last_at <= 12
                and not any(normalized(word) in normalized(gate.last_text) for word in NEGATION_WORDS))


async def inspect_app(gate: VoiceCommandGate) -> dict:
    if not fresh_speech(gate):
        return {'status': 'needs_clarification', 'message': 'قول طلبك عن التطبيق بصوتك.'}
    text = gate.last_text
    action = section_command(text)
    search = find_request(text)
    if action:
        gate.used = True
        label = SECTION_ALIASES[action['section']].split('|')[0]
        return {'status': 'requested', 'message': f'طلبت من واجهة برق تفتح {label}.',
                '_ui': {'type': 'barq_app_action', 'app_action': action}}
    if search:
        gate.used = True
        scope, query = search
        if not 2 <= len(query) <= 100:
            return {'status': 'needs_clarification', 'message': 'قول اسم أقصر للبحث.'}
        data = await asyncio.to_thread(search_catalogue, scope, query)
        return {'status': data['status'], 'items': data['items'],
                'message': ('نتائج من كتالوج برق.' if data['items'] else
                            'المصدر مش متاح حاليًا.' if data['status'] == 'unavailable' else 'مفيش نتيجة مطابقة.')}
    if not re.search(r'برق|barq|التطبيق|القسم|الواجهه|الواجهة|الصفحه|الصفحة|الموسيقي|الاغاني|السينما|الفيلم|الكتاب|المكتبه|المكتبة|الادوات|\b(?:app|section|cinema|music|library|books?|tools?|current view)\b', normalized(text)):
        return {'status': 'needs_clarification', 'message': 'اسألني عن قسم أو محتوى جوه برق.'}
    return {**read_context(), 'sections': {key: names.split('|')[0] for key, names in SECTION_ALIASES.items()}}
