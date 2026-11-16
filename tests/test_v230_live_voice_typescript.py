"""Regression: Windows frontend build must not hit TS6133 in the Live voice bridge.

This module is standalone (DOM / ES builtins), so it can be typechecked
before installing React dependencies when a `tsc` executable is available.
The normal `npm run typecheck` remains the authoritative full UI gate.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'frontend' / 'src' / 'lib' / 'liveVoice.ts'


def test_live_voice_is_typechecked_with_unused_checks():
    compiler = ROOT / 'frontend' / 'node_modules' / 'typescript' / 'bin' / 'tsc'
    if compiler.is_file():
        node = shutil.which('node')
        if not node:
            pytest.skip('Node.js is not installed')
        command = [node, str(compiler)]
    else:
        executable = shutil.which('tsc')
        if not executable:
            pytest.skip('TypeScript is unavailable; full UI typecheck runs in the Windows builder')
        command = [executable]

    result = subprocess.run(
        command + [
            '--noEmit', '--noUnusedLocals', '--noUnusedParameters',
            '--target', 'ES2022', '--module', 'ESNext',
            '--moduleResolution', 'bundler', '--lib', 'ES2022,DOM',
            '--pretty', 'false', str(MODULE),
        ],
        cwd=ROOT / 'frontend', text=True, capture_output=True, timeout=45,
    )
    assert result.returncode == 0, (
        'LiveVoice TypeScript standalone typecheck failed:\n' + result.stdout + result.stderr
    )


def test_open_conversation_mode_is_forwarded_to_live_socket():
    content = MODULE.read_text(encoding='utf-8')
    assert "mode=${openConversation?'open':'standard'}" in content
    assert 'private detectEndOfSpeech(' in content
    assert "type:'end_audio'" in content
