"""Regression checks for recovery build without masking errors."""
from pathlib import Path
import json
import os
import tempfile
from types import SimpleNamespace
from scripts import build_short_path as builder

ROOT=Path(__file__).resolve().parents[1]

def test_git_refresh_button_is_a_void_handler():
    source=(ROOT/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    assert 'onClick={()=>tree&&void requestJSON' not in source
    assert 'onClick={()=>{if (!tree) return; void requestJSON<Git>' in source

def test_recovery_uses_bundled_ui_but_preserves_exe_gate():
    script=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert '[switch]$UseBundledUI' in script
    assert 'if ($UseBundledUI)' in script
    assert 'Bundled React reference missing' in script
    assert 'npm run build' in script
    assert "Smoke-testing the actual packaged Windows executable" in script
    assert "Building Windows Setup.exe (Inno Setup)" in script
    assert script.index('npm run build') < script.index("'-m', 'PyInstaller'")

def test_bundled_ui_entry_refers_to_real_assets():
    import re
    root=ROOT/'web/react'
    html=(root/'index.html').read_text(encoding='utf-8')
    paths=re.findall(r'(?:src|href)="(/assets/[^"]+)"',html)
    assert len(paths)>=2
    for path in paths:
        target=root/path.lstrip('/')
        assert target.is_file() and target.stat().st_size > 0

def test_recovery_command_propagates_through_staging(tmp_path):
    p=tmp_path/'src'
    (p/'scripts').mkdir(parents=True)
    (p/'scripts/installer.iss').write_text('#define AppVersion "1.2.3"')
    (p/'web/react/assets').mkdir(parents=True)
    (p/'web/react/index.html').write_text('<!doctype html>')
    def runner(command,cwd,check):
        assert command[-2:] == ['-UseBundledUI','-StagedBuild']
        raise RuntimeError('test runner stops before packaging')
    import pytest
    # The real installer uses a short staging folder. Under Windows, pytest's
    # tmp_path can be >80 chars long; testing through that path is not realistic.
    base = builder.build_base() if os.name == 'nt' else tmp_path/'base'
    base.mkdir(parents=True, exist_ok=True)
    with pytest.raises(RuntimeError,match='test runner stops'):
        builder.run_build(p,base,runner=runner,bundled_ui=True)
