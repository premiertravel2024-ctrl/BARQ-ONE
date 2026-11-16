from core.version import VERSION
"""Regression checks for the reported 4 TypeScript build errors and packaging."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def test_network_map_drops_unused_refreshcw_import():
    ui=(ROOT/'frontend/src/components/network/NetworkMap.tsx').read_text(encoding='utf-8')
    assert 'RefreshCw' not in ui
    assert 'export function NetworkMap' in ui

def test_workspace_activity_icons_are_resolved():
    ui=(ROOT/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    imports=ui.split("from 'lucide-react'")[0].split('import {')[-1]
    imported={name.strip() for name in imports.strip().rstrip('}').split(',')}
    assert {'Folder','FolderOpen','FileCode2','ChevronDown','ChevronRight'} <= imported
    assert "['explorer','الملفات',Folder]" in ui

def test_build_requires_typescript_vite_before_pyinstaller():
    ps=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert "npm run build" in ps
    assert ps.index("npm run build") < ps.index("'-m', 'PyInstaller'")
    assert "if (-not (Test-Path 'web/react/index.html'))" in ps

def test_all_active_build_versions_match():
    pkg=json.loads((ROOT/'frontend/package.json').read_text(encoding='utf-8'))
    lock=json.loads((ROOT/'frontend/package-lock.json').read_text(encoding='utf-8'))
    v=VERSION
    assert pkg['version']==v
    assert lock['version']==v
    assert lock['packages']['']['version']==v
    for file in ['scripts/build_windows.ps1','scripts/installer.iss','BUILD_BARQ.bat','BUILD_WINDOWS_EXE.bat','.github/workflows/windows-build.yml']:
        assert v in (ROOT/file).read_text(encoding='utf-8')
