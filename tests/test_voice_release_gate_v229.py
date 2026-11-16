"""The frozen application must contain the internal wake runtime, not just UI."""
from pathlib import Path


def test_exe_self_test_checks_internal_microphone_dependencies():
    root=Path(__file__).resolve().parents[1]
    desktop=(root/'desktop.py').read_text()
    release=(root/'scripts/build_windows.ps1').read_text()
    assert "if getattr(sys, 'frozen', False):" in desktop
    assert 'wake_runtime_bundled' in desktop
    assert 'from voice.wake_fingerprint import signature' in desktop
    assert '-not $smoke.voice_runtime_bundled' in release
