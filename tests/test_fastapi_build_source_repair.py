"""Check stale BARQ API sources fail early instead of failing 11 pytest imports."""
from pathlib import Path
import importlib.util
import subprocess
import sys
from textwrap import dedent
ROOT=Path(__file__).resolve().parents[1]

def _load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_shipped_source_guard_accepts_modern_api():
    checker=_load('fastapi_build_guard',ROOT/'scripts'/'verify_fastapi_build_source.py')
    assert checker.check_source(ROOT)==0

def test_guard_catches_stale_source_before_any_python_tests(tmp_path):
    checker=_load('fastapi_build_guard2',ROOT/'scripts'/'verify_fastapi_build_source.py')
    (tmp_path/'api.py').write_text("from fastapi import FastAPI\napp=FastAPI(title='BARQ')\napp.add_event_handler('startup', lambda: None)\n",encoding='utf-8')
    assert checker.check_source(tmp_path)==3

def test_repair_can_be_applied_twice_and_preserves_backup(tmp_path):
    src=(ROOT/'api.py').read_text(encoding='utf-8')
    # Fixture recreates the exact unpatched startup structure in v2.30.
    current = "app=FastAPI(title='BARQ', lifespan=barq_lifespan)"
    assert current in src
    import re
    src=re.sub(r'(?s)# Use a lifespan callback.*?app=FastAPI\(title=\'BARQ\', lifespan=barq_lifespan\)',"app=FastAPI(title='BARQ')",src,count=1)
    src=src.replace('# Startup is installed through barq_lifespan above.',"app.add_event_handler('startup', restart_consented_file_index)")
    assert "app.add_event_handler('startup', restart_consented_file_index)" in src
    (tmp_path/'api.py').write_text(src,encoding='utf-8')
    (tmp_path/'BUILD_BARQ.bat').write_text('echo build',encoding='ascii')
    fixer=_load('barq_repair_fastapi', ROOT/'scripts'/'repair_fastapi_build.py')
    # This file is not importable by name until scripts/ is on sys.path.
    sys.path.insert(0,str(ROOT/'scripts'))
    try:
        assert fixer.run(tmp_path)==0
        assert fixer.run(tmp_path)==0
    finally:
        sys.path.pop(0)
    assert (tmp_path/'api.py.before-fastapi-repair.bak').read_text(encoding='utf-8')==src
    assert "app.add_event_handler('startup'," not in (tmp_path/'api.py').read_text(encoding='utf-8')

def test_staged_builder_hash_check_is_present():
    builder=(ROOT/'scripts'/'build_short_path.py').read_text(encoding='utf-8')
    assert 'source_sha != stage_sha' in builder
    win=(ROOT/'scripts'/'build_windows.ps1').read_text(encoding='utf-8')
    assert 'verify_fastapi_build_source.py' in win
    assert '--runtime' in win
