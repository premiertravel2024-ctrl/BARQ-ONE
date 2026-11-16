"""Regression contracts for the independently configured BARQ voice assistant."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_assistant_settings_speaker_can_switch_without_replacing_gemini_default():
    ui=(ROOT/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    client=(ROOT/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text(encoding='utf-8')
    server=(ROOT/'api.py').read_text(encoding='utf-8')
    assert "useState<'gemini'|'local'>('gemini')" in ui
    assert "'/v1/voice/speaker'" in ui
    assert 'Gemini Live — صوت Google (الافتراضي)' in ui
    assert 'محلي — Whisper و Windows SAPI (تجريبي)' in ui
    assert "current.speaker==='local'?new LocalVoice(onEvent):new LiveVoice(onEvent)" in client
    assert "@app.post('/v1/voice/speaker')" in server


def test_local_results_not_persisted_as_history_or_external_gemini_context():
    strip=(ROOT/'frontend/src/components/chat/VoiceResultsStrip.tsx').read_text(encoding='utf-8')
    handler=(ROOT/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text(encoding='utf-8')
    assert "window.addEventListener('barq-handsfree-state',onState)" in strip
    assert "new CustomEvent('barq-voice-local-cards'" in handler
    fragment=handler.split("if(message.type==='barq_cards'",1)[1].split("if(message.type==='unverified_voice_claim'",1)[0]
    assert 'saveConversation' not in fragment and 'addMessage' not in fragment
