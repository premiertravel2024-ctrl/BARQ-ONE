"""Regression: do not block a valid release because of an obsolete UI marker."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'scripts/verify_desktop_consent_bundle.py'
_spec=importlib.util.spec_from_file_location('barq_desktop_consent_compiled_gate', MODULE)
assert _spec and _spec.loader
_mod=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _copy_source(root):
    for relative in _mod.SOURCE_CONTRACTS:
        p=root/relative
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text((ROOT/relative).read_text(encoding='utf-8'),encoding='utf-8')


def test_valid_compiled_consent_does_not_require_obsolete_marker(tmp_path):
    _copy_source(tmp_path)
    assets=tmp_path/'web/react/assets'
    assets.mkdir(parents=True)
    # Simulates minified output split into multiple JS chunks.
    items=list(_mod.BUNDLE_CONTRACTS.values())
    (assets/'index-a.js').write_text(''.join(f'"{x}";' for x in items[:3]),encoding='utf-8')
    (assets/'index-b.js').write_text(''.join(f'"{x}";' for x in items[3:]),encoding='utf-8')
    assert _mod.check(tmp_path)==[]


def test_missing_consent_setting_blocks_release(tmp_path):
    _copy_source(tmp_path)
    assets=tmp_path/'web/react/assets'
    assets.mkdir(parents=True)
    items=[x for k,x in _mod.BUNDLE_CONTRACTS.items() if k!='computer control opt-in']
    (assets/'index.js').write_text(''.join(f'"{x}";' for x in items),encoding='utf-8')
    assert any('computer control opt-in' in x for x in _mod.check(tmp_path))


def test_source_wiring_is_required_even_if_bundle_has_text(tmp_path):
    _copy_source(tmp_path)
    target=tmp_path/'frontend/src/components/workspace/ComputerControl.tsx'
    target.write_text(target.read_text().replace('checked={setting.enabled}','checked={false}'),encoding='utf-8')
    assets=tmp_path/'web/react/assets'
    assets.mkdir(parents=True)
    (assets/'index.js').write_text(' '.join(_mod.BUNDLE_CONTRACTS.values()),encoding='utf-8')
    assert any('checked={setting.enabled}' in x for x in _mod.check(tmp_path))


def test_builder_runs_semantic_gate_after_fresh_build():
    builder=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert "Invoke-Step 'Type-checking and building React UI' { npm run build }" in builder
    assert "(Join-Path $PSScriptRoot 'verify_desktop_consent_bundle.py') --root $root" in builder
    assert "Select-String -LiteralPath $_.FullName -SimpleMatch -Pattern 'v2.30.0-desktop-consent-tooltip-fix'" not in builder
