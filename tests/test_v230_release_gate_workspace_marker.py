"""Release gate regression: new Studio UI must retain the compiled release token."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
from core.version import VERSION
MARKER = f'v{VERSION}-build-gated-ui'
WORK_CENTER = f'v{VERSION}-work-center-ui-audit'


def test_workspace_keeps_immutable_release_marker_and_independent_ui_marker():
    source = (ROOT / 'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text(encoding='utf-8')
    app=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
    assert f'data-release-marker="{MARKER}"' in app
    assert '<WorkspaceStudio' not in app
    assert f'data-studio-version="{WORK_CENTER}"' in source


def test_preflight_release_metadata_green():
    path = ROOT / 'scripts/verify_release_consistency.py'
    spec = importlib.util.spec_from_file_location('barq_verify_release_consistency', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.verify() == []


def test_windows_build_keeps_fresh_bundle_guard():
    source = (ROOT / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert f"$studioMarker = '{MARKER}'" in source
    assert 'Fresh React build did not contain' in source
    assert "Invoke-Step 'Type-checking and building React UI' { npm run build }" in source
