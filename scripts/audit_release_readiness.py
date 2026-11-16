"""Dependency-free BARQ release gate. Fail before creating an installer.

This checks source integrity and critical voice contracts. Hardware/online
Gemini tests are deliberately NOT claimed by this source-only verification.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CRITICAL_FILES=(
    'desktop.py', 'voice/live.py','voice/wake.py','voice/direct_wake.py',
    'frontend/src/lib/liveVoice.ts',
    'frontend/src/components/chat/LiveVoiceDialog.tsx',
    'frontend/public/audio/live-capture.js',
    'scripts/build_windows.ps1','scripts/installer_update.iss',
    'scripts/build_barq_update_kit.ps1',
    'scripts/verify_voice_build_dependencies.py',
    'requirements-desktop.txt', 'frontend/package-lock.json',
    'tests/test_v229_bounded_live_uplink.py',
)


def audit(root:Path=ROOT):
    failures=[]
    checked=[]
    for name in CRITICAL_FILES:
        p=root/name
        if not p.is_file() or p.stat().st_size==0:
            failures.append('Missing/empty required release file: '+name)
        else:
            checked.append(name)
    if failures:
        return {'status':'failed','checked':checked,'failures':failures}

    for src in root.rglob('*.py'):
        if any(part in {'.buildvenv','.venv','venv','node_modules','dist','build','vendor'} for part in src.relative_to(root).parts):
            continue
        try:
            compile(src.read_bytes(),str(src),'exec',dont_inherit=True)
        except Exception as exc:
            failures.append(f'Python syntax failed at {src.relative_to(root)}: {type(exc).__name__}')
    web=(root/'frontend/public/audio/live-capture.js').read_text(encoding='utf-8')
    frontend=(root/'frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    backend=(root/'voice/live.py').read_text(encoding='utf-8')
    update=(root/'scripts/installer_update.iss').read_text(encoding='utf-8')
    main_setup=(root/'scripts/installer.iss').read_text(encoding='utf-8')
    packages=json.loads((root/'frontend/package.json').read_text(encoding='utf-8'))
    package_lock=json.loads((root/'frontend/package-lock.json').read_text(encoding='utf-8'))
    for flag,ok in (
        ('Browser and worklet identifiers match',
         "registerProcessor('barq-capture'" in web and
         "new AudioWorkletNode(this.input,'barq-capture')" in frontend),
        ('Websocket audio relay and end-of-utterance present',
         'send_realtime_input' in backend and 'BoundedLiveAudioUplink' in backend and
         "type:'end_audio'" in frontend and "msg.get('type')=='end_audio'" in backend),
        ('React dependencies have a frozen npm lockfile',
         packages.get('name')==package_lock.get('name') and
         'esbuild' in packages.get('devDependencies',{})),
        ('Setup and update use the same app identifier',
         '9BB70D04-1EC5-4BC6-B811-64B08F5C8977' in main_setup and
         '9BB70D04-1EC5-4BC6-B811-64B08F5C8977' in update),
        ('Update preserves local wake model',
         r'\models\wake' not in update.split('[UninstallDelete]')[-1] if '[UninstallDelete]' in update else
         '[UninstallDelete]' not in update),
    ):
        if not ok:
            failures.append('Release contract failed: '+flag)
    return {'status':'ok' if not failures else 'failed',
            'checked':checked,'failures':failures,
            'python_files_scanned':sum(1 for p in root.rglob('*.py') if not any(
                part in {'.buildvenv','.venv','venv','node_modules','dist','build','vendor'}
                for part in p.relative_to(root).parts))}


def main():
    result=audit()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='ok' else 1

if __name__=='__main__':
    sys.exit(main())
