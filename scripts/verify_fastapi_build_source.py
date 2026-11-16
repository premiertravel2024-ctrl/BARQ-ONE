#!/usr/bin/env python3
"""Print the exact BARQ source and verify FastAPI startup at build-time."""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path
import sys
import traceback

def check_source(root: Path) -> int:
    api = (root / 'api.py').resolve()
    print(f'[BARQ SOURCE] api.py: {api}', flush=True)
    if not api.is_file():
        print('[BARQ ERROR] api.py missing from staged source.', file=sys.stderr, flush=True)
        return 2
    source = api.read_text(encoding='utf-8-sig')
    print(f'[BARQ SOURCE] api.py sha256: {hashlib.sha256(source.encode("utf-8")).hexdigest()}', flush=True)
    try:
        tree = ast.parse(source, filename=str(api))
    except SyntaxError:
        traceback.print_exc()
        return 2
    legacy_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'add_event_handler']
    if legacy_calls:
        locs = ', '.join(str(node.lineno) for node in legacy_calls)
        print(f'[BARQ ERROR] Old FastAPI add_event_handler still used at api.py line(s) {locs}.',
              file=sys.stderr, flush=True)
        print('[BARQ HELP] Apply FIX_AND_BUILD_BARQ.bat in the source folder shown above, '
              r'NOT in AppData\Local\Bq\b.', file=sys.stderr, flush=True)
        return 3
    apps = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == 'FastAPI']
    if not any(any(k.arg == 'lifespan' for k in node.keywords) for node in apps):
        print('[BARQ ERROR] FastAPI app lacks lifespan startup registration.',
              file=sys.stderr, flush=True)
        return 4
    print('[BARQ PASS] api.py has lifespan startup and no legacy FastAPI event call.', flush=True)
    return 0

def check_runtime(root: Path) -> int:
    # This check runs ONLY after dependencies have been installed in the
    # isolated staging venv. Show the full traceback, never a truncated dot line.
    sys.path.insert(0, str(root))
    try:
        import fastapi, starlette, api
        print(f'[BARQ RUNTIME] FastAPI {fastapi.__version__}, Starlette {starlette.__version__}', flush=True)
        print(f'[BARQ RUNTIME] Loaded BARQ API from: {Path(api.__file__).resolve()}', flush=True)
        if Path(api.__file__).resolve() != (root / 'api.py').resolve():
            raise RuntimeError('Imported API is not the staged source being built')
        if not callable(api.app.router.lifespan_context):
            raise RuntimeError('Startup lifespan is not callable')
    except Exception:
        print('[BARQ ERROR] Full traceback for API import/startup:', file=sys.stderr, flush=True)
        traceback.print_exc()
        return 5
    print('[BARQ PASS] Staged FastAPI import + lifespan check passed.', flush=True)
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    print(f'[BARQ SOURCE] Root: {root}', flush=True)
    result = check_source(root)
    if result or not args.runtime: return result
    return check_runtime(root)

if __name__ == '__main__':
    raise SystemExit(main())
