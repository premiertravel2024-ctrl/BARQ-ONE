"""Fail closed on missing *functional* computer/voice consent wiring in a fresh React build.

A previous build gate looked for a retired release label that was never shipped in
current TypeScript source. That produced false failures after a valid Vite build.
This gate inspects actual routes, opt-in UI and the emitted JS; a random token
or a comment in a source file cannot be used as evidence of functioning consent.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# These strings are functional user-facing labels/routes/events, rather than
# a build-time marker that can become stale after UI refactoring.
BUNDLE_CONTRACTS = {
    'computer policy endpoint': '/v1/computer/settings',
    'computer control opt-in': 'Enable computer interaction',
    'voice permission change event': 'barq-voice-computer-permission-updated',
    'voice wake permission field': 'wake_computer_enabled',
    'computer status endpoint': '/v1/computer/status',
}

SOURCE_CONTRACTS = {
    'frontend/src/components/workspace/ComputerControl.tsx': (
        "'/v1/computer/settings'", 'checked={setting.enabled}',
        'onChange={e=>{void update({enabled:e.target.checked})}}',
        'Enable computer interaction',
    ),
    'frontend/src/components/layout/VoiceSettings.tsx': (
        'barq-voice-computer-permission-updated', 'wake_computer_enabled',
    ),
    'frontend/src/App.tsx': (
        'refreshComputerVoiceConsent', '/v1/computer/status',
        '/v1/voice/wake/control', 'consentedComputerVoice=allowed',
        'barq-voice-computer-permission-updated',
    ),
}


def check(root: Path, *, source_only: bool = False) -> list[str]:
    problems: list[str] = []
    for relative, contracts in SOURCE_CONTRACTS.items():
        try:
            source = (root / relative).read_text(encoding='utf-8')
        except OSError as error:
            problems.append(f'Missing consent source: {relative}: {error}')
            continue
        for contract in contracts:
            if contract not in source:
                problems.append(f'Consent implementation missing {contract!r} in {relative}')
    if source_only:
        return problems
    asset_dir = root / 'web/react/assets'
    js_files = list(asset_dir.glob('*.js'))
    if not js_files:
        return problems + [f'No compiled JavaScript assets found in {asset_dir}']
    # Search all output chunks; a production build can split the computer UI.
    # Do not concatenate megabytes of JavaScript into one large in-memory string.
    found = set()
    for file in js_files:
        try:
            chunk = file.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as error:
            problems.append(f'Unreadable React JS asset {file.name}: {error}')
            continue
        for name, contract in BUNDLE_CONTRACTS.items():
            if contract in chunk:
                found.add(name)
    for name in BUNDLE_CONTRACTS:
        if name not in found:
            problems.append(f'Fresh React build missing computer consent contract: {name}')
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source-only', action='store_true', help='Check opt-in source wiring before running npm')
    args = parser.parse_args()
    problems = check(args.root.resolve(), source_only=args.source_only)
    if problems:
        for problem in problems:
            print('BARQ CONSENT BUNDLE ERROR: ' + problem, file=sys.stderr)
        return 1
    print('BARQ computer/voice consent source wiring verified.' if args.source_only else
          'BARQ React computer/voice consent settings verified in fresh JS bundle.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
