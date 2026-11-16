"""Regression tests for release completeness before attempting npm/PyInstaller on Windows."""
from pathlib import Path
import json
from scripts.verify_source_integrity import ROOT, verify


def test_complete_release_passes_local_gate():
    assert verify(ROOT) == []


def test_gate_reports_missing_required_files(tmp_path):
    errors = verify(tmp_path)
    assert any('build/jobs.py' in error for error in errors)
    assert any('WorkspaceStudio.tsx' in error for error in errors)


def test_gate_finds_broken_relative_import(tmp_path):
    source = tmp_path / 'frontend' / 'src'
    source.mkdir(parents=True)
    (source / 'Bad.tsx').write_text("import {X} from './missing-component';\nexport default X;\n", encoding='utf-8')
    errors = verify(tmp_path)
    assert any('Missing frontend import:' in error and 'missing-component' in error for error in errors)


def test_gate_finds_lockfile_dependency_mismatch(tmp_path):
    frontend = tmp_path / 'frontend'
    frontend.mkdir()
    (frontend / 'package.json').write_text(json.dumps({'dependencies': {'react': '18.3.1'}}))
    (frontend / 'package-lock.json').write_text(json.dumps({'packages': {'': {'dependencies': {'react': '17.0.0'}}}}))
    errors = verify(tmp_path)
    assert any('Lockfile root dependencies' in error for error in errors)


def test_every_official_build_entrypoint_uses_early_gate():
    ui = (ROOT / 'CHECK_BARQ_UI.bat').read_text(encoding='utf-8')
    ps = (ROOT / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    workflow = (ROOT / '.github/workflows/windows-build.yml').read_text(encoding='utf-8')
    assert ui.index('verify_source_integrity.py') < ui.index('npm ci')
    assert ps.index('verify_source_integrity.py') < ps.index('npm ci')
    assert workflow.index('verify_source_integrity.py') < workflow.index('npm ci')


def test_workspace_layout_type_imported_from_hooks():
    studio = (ROOT / 'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    assert 'type Layout}' in studio
    assert 'Partial<Layout>' in studio


def test_integrity_gate_rejects_missing_workspace_layout_type(tmp_path):
    source = tmp_path / 'frontend/src/components/workspace'
    source.mkdir(parents=True)
    (source / 'studioHooks.ts').write_text('export type Layout={side:number};', encoding='utf-8')
    (source / 'WorkspaceStudio.tsx').write_text(
        "import {DEFAULT_LAYOUT} from './studioHooks';\n"
        "type SavedState={layout?:Partial<Layout>};\n", encoding='utf-8'
    )
    errors = verify(tmp_path)
    assert any('Undefined TypeScript type Layout' in error for error in errors)


def test_integrity_gate_accepts_imported_workspace_layout_type(tmp_path):
    source = tmp_path / 'frontend/src/components/workspace'
    source.mkdir(parents=True)
    (source / 'studioHooks.ts').write_text('export type Layout={side:number};', encoding='utf-8')
    (source / 'WorkspaceStudio.tsx').write_text(
        "import {type Layout} from './studioHooks';\n"
        "type SavedState={layout?:Partial<Layout>};\n", encoding='utf-8'
    )
    errors = verify(tmp_path)
    assert not any('Undefined TypeScript type Layout' in error for error in errors)
