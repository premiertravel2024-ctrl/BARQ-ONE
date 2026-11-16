"""Regression check for custom IconButton live-voice callback type."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_composer_live_voice_event_handler_returns_void():
    composer=(ROOT/'frontend/src/components/chat/Composer.tsx').read_text(encoding='utf-8')
    button=(ROOT/'frontend/src/components/ui/Button.tsx').read_text(encoding='utf-8')
    assert "onClick?:(e:MouseEvent<HTMLButtonElement>)=>void|Promise<unknown>" in button
    # The composer still has text and attachments only.
    assert 'handsfreeActive' not in composer
    assert 'MicOff' not in composer and 'AudioLines' not in composer
    assert "onClick={()=>window.dispatchEvent(" not in composer
    # The event bridge must be mounted: a correct-looking button with no
    # listener is still broken.
    app=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
    controller=(ROOT/'frontend/src/components/chat/HandsFreeVoice.tsx').read_text(encoding='utf-8')
    assert "window.addEventListener('barq-start-live-voice',open)" in app
    assert "window.addEventListener('barq-handsfree-start',onStart)" in controller
    assert "window.addEventListener('barq-handsfree-stop',onStop)" in controller
    assert "new CustomEvent('barq-handsfree-state',{detail:voiceState})" in controller
    assert "updateVoiceState({active:false,phase:'idle'" in controller
    assert "updateVoiceState({active:true,phase:'connecting'" in controller
