#!/usr/bin/env python3
"""Idempotent startup compatibility repair, limited to known BARQ v2.30."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import shutil
import sys

LEGACY_APP = "app=FastAPI(title='BARQ')"
LEGACY_EVENT = "app.add_event_handler('startup', restart_consented_file_index)"
LIFESPAN = """# BARQ FastAPI startup compatibility (modern lifespan API).
from contextlib import asynccontextmanager

@asynccontextmanager
async def barq_lifespan(_app: FastAPI):
    restart_consented_file_index()
    yield

app=FastAPI(title='BARQ', lifespan=barq_lifespan)"""

def run(root: Path) -> int:
    root = root.resolve()
    if not (root/'BUILD_BARQ.bat').is_file() and (root/'BARQ'/'BUILD_BARQ.bat').is_file():
        root = root/'BARQ'
    target = root/'api.py'
    print(f'[BARQ] Repair target: {target}',flush=True)
    if not target.is_file():
        print('[ERROR] api.py not found. Unzip the patch in the real BARQ source folder, '
              'beside BUILD_BARQ.bat.',file=sys.stderr)
        return 2
    original = target.read_text(encoding='utf-8-sig')
    if "app=FastAPI(title='BARQ', lifespan=barq_lifespan)" in original and LEGACY_EVENT not in original:
        print('[BARQ] Already fixed: FastAPI lifespan is installed.',flush=True)
    elif original.count(LEGACY_APP) == 1 and original.count(LEGACY_EVENT) == 1:
        updated = original.replace(LEGACY_APP, LIFESPAN, 1)
        updated = updated.replace(LEGACY_EVENT, '# Startup is registered via barq_lifespan.', 1)
        ast.parse(updated,filename=str(target))
        backup=target.with_name('api.py.before-fastapi-repair.bak')
        if not backup.exists(): shutil.copy2(target,backup)
        target.write_text(updated,encoding='utf-8')
        print(f'[BARQ] Applied lifespan fix. Backup: {backup}',flush=True)
    else:
        print('[ERROR] api.py has an unexpected version or startup structure. '
              'No changes made. Use the matching full source ZIP.',file=sys.stderr)
        return 3
    print('[BARQ] Checking the actual source before Windows build...',flush=True)
    from verify_fastapi_build_source import check_source
    return check_source(root)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    raise SystemExit(run(args.root))
