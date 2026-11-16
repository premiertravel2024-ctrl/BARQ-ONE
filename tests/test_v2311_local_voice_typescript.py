"""Regression: strict TS compilation for the optional local voice module.

This check catches the TS2367 MediaRecorder state narrowing and the TS2322
DOM event callback signatures that blocked BARQ's Windows frontend build.
It compiles the real modules with TypeScript rather than matching text alone.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'frontend' / 'src' / 'lib' / 'localVoice.ts'


def test_local_voice_strict_dom_typecheck():
    local_tsc = ROOT / 'frontend' / 'node_modules' / 'typescript' / 'bin' / 'tsc'
    if local_tsc.is_file():
        node = shutil.which('node')
        if not node:
            pytest.skip('Node.js unavailable; frontend build runs the full typecheck')
        cmd = [node, str(local_tsc)]
    else:
        tsc = shutil.which('tsc')
        if not tsc:
            pytest.skip('TypeScript unavailable; frontend build runs the full typecheck')
        cmd = [tsc]
    cmd += [
        '--noEmit', '--pretty', 'false', '--strict', '--noUnusedLocals',
        '--noUnusedParameters', '--skipLibCheck', '--target', 'ES2022',
        '--module', 'ESNext', '--moduleResolution', 'Bundler',
        '--lib', 'ES2022,DOM,DOM.Iterable', str(MODULE),
    ]
    result = subprocess.run(cmd, cwd=ROOT / 'frontend', capture_output=True,
                            text=True, timeout=60, check=False)
    assert result.returncode == 0, (
        'Strict localVoice.ts TypeScript typecheck failed:\n'
        + result.stdout + result.stderr
    )


def test_audio_completion_callbacks_are_dom_event_handlers():
    text = MODULE.read_text(encoding='utf-8')
    assert 'audio.onended=()=>resolve();' in text
    assert "audio.onerror=()=>reject(new Error(" in text
    assert 'audio.onended=resolve;' not in text
    assert "if(recorder.state!=='inactive')recorder.stop();" not in text
