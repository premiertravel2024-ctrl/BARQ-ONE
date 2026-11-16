"""Fast offline BARQ release gate: detect missing/invalid source files before npm or PyInstaller.

Intentionally uses stdlib only; safe to run on developer and CI machines.
This is a completeness/syntax check, NOT a substitute for a real React build.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / 'frontend'
SOURCE = FRONTEND / 'src'
CODE_SUFFIXES = {'.ts', '.tsx', '.js', '.jsx'}
REQUIRED = (
    'api.py', 'desktop.py', 'brain/coordinator.py', 'core/adaptive_resources.py',
    'build/__init__.py', 'build/jobs.py', 'scripts/package_full_source.py', 'core/sqlite.py', 'cache/store.py', 'core/version.py', 'core/json_contracts.py', 'providers/reliability.py',
    'brain/commands.py', 'brain/failures.py', 'brain/understanding.py',
    'scripts/release_evidence.py', 'scripts/smoke_install.ps1', 'workspace/manager.py', 'scripts/build_windows.ps1',
    'scripts/build_short_path.py', 'scripts/create_build_venv.py', 'scripts/run_python_build_tests.py', 'scripts/verify_frontend_lock.py', 'scripts/verify_release_consistency.py',
    'scripts/verify_python_build.py', 'scripts/installer.iss',
    'scripts/chat_coordination_smoke.mjs', 'BUILD_BARQ.bat',
    'BUILD_WINDOWS_EXE.bat', 'CHECK_BARQ_UI.bat', 'CHECK_BARQ_PYTHON_VENV.bat',
    'frontend/package.json', 'frontend/package-lock.json',
    'frontend/vite.config.ts', 'frontend/tsconfig.json',
    'frontend/src/main.tsx', 'frontend/src/App.tsx',
    'frontend/src/components/ui/BrandMark.tsx',
    'frontend/src/components/workspace/WorkspaceStudio.tsx',
    'frontend/src/lib/workspaceSync.ts', 'frontend/tests/workspace-sync.ts',
    'core/processes.py', 'core/generation.py', 'coding/source_contract.py', 'mission/validation.py', 'brain/live_code.py', 'frontend/src/components/workspace/AgentCodePanel.tsx',
    'frontend/src/components/workspace/PreviewPanel.tsx',
    'frontend/src/components/layout/SettingsModal.tsx',
    'frontend/src/components/layout/PerformanceSettings.tsx',
    'frontend/src/components/chat/ApprovalDialog.tsx', 'frontend/src/lib/taskActions.ts', 'frontend/src/lib/approvals.ts', 'frontend/tests/approval-flow.ts',
    'frontend/public/brand/barq-mark-light.png',
    'frontend/public/brand/barq-mark-dark.png',
    'frontend/public/favicon.png',
    'frontend/public/audio/live-capture.js',
    'api_routes/listening_rooms.py',
    'frontend/src/components/listening/ListeningRoom.tsx',
    'execution/__init__.py', 'execution/runner.py', 'execution/service.py',
    'execution/services.py', 'execution/doctor.py', 'execution/grants.py',
    'execution/known_folders.py', 'execution/recipes.py', 'execution/react_mission.py',
    'scripts/windows_e2e.py', 'RUN_WINDOWS_E2E.bat',
    'voice/computer_tools.py',
    'frontend/src/lib/liveVoice.ts',
    'frontend/src/components/chat/LiveVoiceDialog.tsx',
)
# Restrict paths to local source modules; third-party packages are handled by npm ci.
RELATIVE_IMPORT = re.compile(
    r"\b(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?['\"](\.{1,2}/[^'\"]+)['\"]"
    r"|\bimport\s*\(\s*['\"](\.{1,2}/[^'\"]+)['\"]\s*\)"
)
ASSET_REFERENCE = re.compile(r"['\"](/(?:brand|fonts|favicon)[^'\"?]*)['\"]")


def resolve_local(from_file: Path, relative: str) -> bool:
    candidate = from_file.parent / relative
    options = (candidate, *(Path(str(candidate) + suffix) for suffix in CODE_SUFFIXES),
               candidate.with_suffix('.json'), *(candidate / ('index' + suffix) for suffix in CODE_SUFFIXES))
    return any(path.is_file() for path in options)


def verify(root: Path = ROOT) -> list[str]:
    frontend = root / 'frontend'
    source = frontend / 'src'
    errors: list[str] = []
    for relative in REQUIRED:
        if not (root / relative).is_file():
            errors.append(f'Missing required release file: {relative}')
    for file in root.rglob('*.py'):
        if any(part in {'node_modules', 'dist', '.buildvenv', '__pycache__', '.venv'} for part in file.parts):
            continue
        try:
            ast.parse(file.read_text(encoding='utf-8-sig'), filename=str(file))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            errors.append(f'Invalid Python source {file.relative_to(root)}: {exc}')
    if source.is_dir():
        files = sorted(file for file in source.rglob('*') if file.suffix in CODE_SUFFIXES)
        if len(files) < 20:
            errors.append(f'Frontend appears incomplete (only {len(files)} source files)')
        for file in files:
            content = file.read_text(encoding='utf-8-sig')
            for match in RELATIVE_IMPORT.finditer(content):
                relative = match.group(1) or match.group(2)
                if relative and not resolve_local(file, relative):
                    errors.append(f'Missing frontend import: {file.relative_to(root)} -> {relative}')
            for match in ASSET_REFERENCE.finditer(content):
                asset = match.group(1).lstrip('/')
                if not (frontend / 'public' / asset).is_file():
                    errors.append(f'Missing frontend asset: {file.relative_to(root)} -> /{asset}')
    # Guard a real v2.17 regression: WorkspaceStudio references Layout inside a
    # type parameter, but `Layout` was omitted when layout state was extracted
    # to studioHooks. A missing type compiles as syntax yet fails `tsc` (TS2304).
    studio = source / 'components' / 'workspace' / 'WorkspaceStudio.tsx'
    hooks = source / 'components' / 'workspace' / 'studioHooks.ts'
    if studio.is_file() and hooks.is_file():
        studio_text = studio.read_text(encoding='utf-8-sig')
        hooks_text = hooks.read_text(encoding='utf-8-sig')
        if re.search(r'\b(?:Partial\s*<\s*Layout\s*>|Layout\s*[;|}>])', studio_text):
            imports = re.findall(
                r"\bimport\s*\{([^}]*)\}\s*from\s*['\"]\./studioHooks['\"]",
                studio_text, flags=re.DOTALL,
            )
            has_import = any(re.search(r'(?<![\w])(?:type\s+)?Layout(?:\s+as\s+\w+)?(?![\w])', names) for names in imports)
            if not has_import:
                errors.append('Undefined TypeScript type Layout in WorkspaceStudio.tsx: import type Layout from ./studioHooks (TS2304)')
            if not re.search(r'\bexport\s+type\s+Layout\b', hooks_text):
                errors.append('Missing exported TypeScript type Layout in studioHooks.ts')
    for relative in ('frontend/package.json', 'frontend/package-lock.json'):
        if not (root / relative).is_file():
            continue
        try:
            parsed = json.loads((root / relative).read_text(encoding='utf-8'))
            if not isinstance(parsed, dict):
                errors.append(f'Invalid JSON object: {relative}')
        except (ValueError, OSError) as exc:
            errors.append(f'Invalid JSON: {relative} ({exc})')
    if (frontend / 'package.json').is_file() and (frontend / 'package-lock.json').is_file():
        try:
            pkg = json.loads((frontend / 'package.json').read_text(encoding='utf-8'))
            lock = json.loads((frontend / 'package-lock.json').read_text(encoding='utf-8'))
            locked = lock.get('packages', {}).get('', {})
            for field in ('dependencies', 'devDependencies'):
                if pkg.get(field, {}) != locked.get(field, {}):
                    errors.append(f'Lockfile root {field} differs from package.json: run npm install --package-lock-only')
        except (ValueError, OSError, AttributeError) as exc:
            errors.append(f'Cannot compare frontend lockfile: {exc}')
    return errors


if __name__ == '__main__':
    failures = verify()
    if failures:
        for error in failures:
            print('BARQ SOURCE INTEGRITY ERROR: ' + error, file=sys.stderr)
        raise SystemExit(1)
    print('BARQ source integrity PASS: all mandatory files, local imports, assets, Python syntax and npm lock metadata.')
