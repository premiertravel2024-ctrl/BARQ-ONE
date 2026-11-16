"""Voice improvements guard actual device rates and owner wake similarity.

This is NOT proof of a person's identity. Unknown speaker samples must not
be authorized to control Windows by the acoustic phrase matcher.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_device_sample_rate_is_resampled_before_sending_16k_pcm():
    capture = (ROOT/'frontend/public/audio/live-capture.js').read_text(encoding='utf-8')
    voice = (ROOT/'frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    assert 'sampleRate/16000' in capture
    assert 'new Int16Array(320)' in capture
    assert 'this.nextOutputPosition' in capture
    assert 'this.input.sampleRate!==16000' not in voice
    assert 'samples.length/16' in voice
    assert (ROOT/'web/react/audio/live-capture.js').read_text(encoding='utf-8') == capture


def test_owner_wake_requires_two_matching_enrollment_samples(monkeypatch):
    from voice import wake_fingerprint as fp
    # Explicitly model a foreign phrase matching just one enrollment sample.
    monkeypatch.setattr(fp, 'signature', lambda sample: 'candidate')
    monkeypatch.setattr(fp, 'similarity', lambda x, y: {'a': .98, 'b': .51, 'c': .50}[y])
    monkeypatch.setattr(fp, 'threshold', lambda templates: .65)
    matched, score = fp.matches(b'untrusted audio', ['a', 'b', 'c'])
    assert not matched and score == .51
    monkeypatch.setattr(fp, 'similarity', lambda x, y: {'a': .98, 'b': .76, 'c': .50}[y])
    assert fp.matches(b'enrolled-sounding audio', ['a', 'b', 'c'])[0]


def test_wake_diagnostics_are_not_biometric_authentication():
    wake = (ROOT/'voice/direct_wake.py').read_text(encoding='utf-8')
    settings = (ROOT/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    assert "speaker_match='not_matched'" in wake
    assert "speaker_match='acoustic_match'" in wake
    assert 'ليست إثباتًا لهوية المتكلم' in settings
