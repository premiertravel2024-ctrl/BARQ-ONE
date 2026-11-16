"""Natural Egyptian speech and explicit, consented Windows toolchain regressions."""
from pathlib import Path

import pytest

from voice.brain_bridge import BARQVoiceBrain, action_route
from voice.command_guard import VoiceCommandGate
from voice.intent import non_executable
from voice.live import live_system_instruction

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('speech,route', [
    ('يا برق، ممكن تفتحلي المفكرة', 'open_on_computer'),
    ('بقولك ايه يا برق ممكن تفتحلي المفكرة', 'open_on_computer'),
    ('محتاجك تشغللي كروم', 'open_on_computer'),
    ('بص شغلي اليوتيوب', 'desktop_companion'),
    ('افتحلي المتصفح', 'open_on_computer'),
    ('كنت عاوزك تدورلي على ملف الفاتورة', 'search_hub'),
    ('بعد اذنك تنقللي ملف وبعدين تقفله', 'start_computer_task'),
    ('ينفع تكمل اللي بتعمله', 'continue_current_work'),
    ('معلش تظبطلي الصوت على 40', 'control_windows_setting'),
    ('بص شوفلي مواصفات الجهاز', 'get_pc_system_facts'),
    ('دور على ملف مواصفات الجهاز', 'search_hub'),
])
def test_natural_egyptian_requests_route_to_real_engine(speech, route):
    assert action_route(speech) == route


@pytest.mark.parametrize('speech', [
    'لو قلت لك تفتحلي المفكرة هتعمل ايه؟',
    'ازاي تفتحلي المفكرة؟',
    'متفتحش المفكرة',
    'لا تشغل كروم',
    'افترض انك تفتحلي المفكرة',
])
@pytest.mark.asyncio
async def test_hypothetical_or_negative_never_executes(speech):
    called = []

    async def dispatcher(*args):
        called.append(args)
        return {'status': 'opened'}

    gate = VoiceCommandGate()
    gate.record(speech)
    result = await BARQVoiceBrain(dispatcher=dispatcher).ask(gate, computer_enabled=True)
    assert result['status'] == 'needs_clarification'
    assert called == []


def test_prompt_natural_and_still_evidence_grounded():
    prompt = live_system_instruction(True)
    assert 'طريقتك في الكلام طبيعية وعفوية' in prompt
    assert 'في الكلام العادي جاوب مباشرة' in prompt
    assert 'Reply naturally in Egyptian Arabic' in prompt
    assert 'not invent steps' in prompt
    assert ' HIGH approval requires an actual on-screen button.' in prompt
    assert 'Say only the returned spoken_ar' not in prompt


def test_toolkit_integrated_and_consent_stays_visible():
    setup = (ROOT / 'scripts/installer.iss').read_text(encoding='utf-8')
    assert 'Source: "..\\INSTALL_BARQ_TOOLKIT.ps1"' in setup
    assert 'Name: toolchain; Description:' in setup
    assert 'Tasks: toolchain; Check: not IsSmoke' in setup
    assert 'Flags: postinstall skipifsilent; Tasks: toolchain' in setup
    assert 'PrivilegesRequired=lowest' in setup
    toolkit = (ROOT / 'INSTALL_BARQ_TOOLKIT.ps1').read_text(encoding='utf-8')
    assert r"'(^|[\\/])\.\.([\\/]|$)'" in toolkit
    assert 'Get-FileHash' in toolkit
    assert 'installed-tools.json' in toolkit


@pytest.mark.parametrize('speech,tool,args', [
    ('ممكن تفتحلي المفكرة', 'open_on_computer', {'request': 'افتح المفكرة'}),
    ('بص شغلي كروم', 'open_on_computer', {'request': 'شغل كروم'}),
    ('ينفع تكمل اللي بتعمله', 'continue_current_work', {}),
])
def test_direct_tool_guard_accepts_natural_user_speech_only(speech, tool, args):
    gate = VoiceCommandGate()
    gate.record(speech, now=10)
    allowed, _ = gate.check(tool, args, now=11)
    assert allowed
    assert not gate.check(tool, args, now=12)[0]


@pytest.mark.parametrize('speech', [
    'ازاي افتح المفكرة', 'لا تفتح المفكرة', 'لو قلت افتح المفكرة'
])
def test_direct_tool_guard_rejects_non_actions(speech):
    gate = VoiceCommandGate()
    gate.record(speech, now=10)
    assert not gate.check('open_on_computer', {'request': 'افتح المفكرة'}, now=11)[0]



def test_colloquial_launch_is_parsed_without_model_target_override():
    from launcher.nlu import parse
    from voice.intent import command_text
    assert parse('محتاجك تشغللي كروم').target_text == 'كروم'
    assert parse(command_text('محتاجك تشغللي كروم')).target_text == 'كروم'
    assert parse(command_text('ينفع تفتحلي المفكرة')).target_text == 'المفكره'
