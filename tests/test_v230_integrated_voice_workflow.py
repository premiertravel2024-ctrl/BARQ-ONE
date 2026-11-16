from pathlib import Path
from voice.command_guard import VoiceCommandGate
from voice.computer_tools import LIVE_COMPUTER_TOOLS, enabled_on_platform
from voice.live import live_system_instruction

ROOT=Path(__file__).resolve().parents[1]

def test_coding_voice_functions_are_explicit_and_no_shell():
    names={a['name'] for a in LIVE_COMPUTER_TOOLS[0]['function_declarations']}
    assert {'current_work_status','continue_current_work'} <= names
    assert 'shell' not in names and 'execute_arbitrary_code' not in names

def test_continuation_requires_recent_speech_and_is_single_use():
    gate=VoiceCommandGate()
    assert not gate.check('continue_current_work',{},now=10)[0]
    gate.record('تابع اللي بتعمله في المشروع',now=10)
    assert gate.check('continue_current_work',{},now=11)[0]
    assert not gate.check('continue_current_work',{},now=12)[0]
    gate.record('لو قلت لك كمل هيحصل إيه',now=13)
    assert not gate.check('continue_current_work',{},now=14)[0]

def test_ambient_audio_cannot_trigger_unrelated_action():
    gate=VoiceCommandGate()
    gate.record('المسلسل شغال في الخلفية',now=30)
    assert not gate.check('open_on_computer',{'request':'افتح المفكرة'},now=31)[0]
    assert not gate.check('stop_computer_task',{},now=31)[0]

def test_work_state_transport_has_no_disk_or_shell_access():
    code=(ROOT/'voice/live.py').read_text(encoding='utf-8')
    assert "msg.get('type')=='work_state'" in code
    assert "('goal','status','phase','summary','progress','task_id')" in code
    assert "'type':'work_continue_requested'" in code

def test_workspace_opens_code_instead_of_user_brief():
    code=(ROOT/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    # The two-pane workspace opens in live-code mode by design. The old test
    # incorrectly demanded the obsolete editor-default UI after that redesign.
    assert "('live'),[codeTarget" in code
    assert "setEditorView('live')" in code
    center=(ROOT/'frontend/src/components/workspace/WorkCenter.tsx').read_text(encoding='utf-8')
    assert 'عرض طلب المشروع الأصلي' in center
    assert '<h2>{mission?.goal' not in center

def test_voice_tone_and_transcript_handling():
    prompt=live_system_instruction(True)
    assert 'Egyptian Arabic' in prompt
    transcript=(ROOT/'frontend/src/lib/voiceTranscript.ts').read_text(encoding='utf-8')
    dialog=(ROOT/'frontend/src/components/chat/LiveVoiceDialog.tsx').read_text(encoding='utf-8')
    assert 'mergeLiveTranscript' in dialog
    assert "flush(false)" in dialog
    assert 'chunk.startsWith(previous)' in transcript
