from core.version import VERSION
"""Make sure the adaptive governor is actually surfaced to settings, not just backend code."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_performance_settings_contains_governor_controls():
    panel = (ROOT/'frontend/src/components/layout/PerformanceSettings.tsx').read_text(encoding='utf-8')
    ui = (ROOT/'frontend/src/components/layout/AdaptiveBrainSettings.tsx').read_text(encoding='utf-8')
    assert '<AdaptiveBrainSettings active={active}/>' in panel
    assert '/v1/system/resources/mode' in ui
    assert '/v1/system/resources' in ui
    assert all(mode in ui for mode in ('eco', 'balanced', 'performance'))
    assert 'ram_available_bytes' in ui and 'logical_cpu_cores' in ui


def test_restored_build_module_and_release_gate():
    assert (ROOT/'build/jobs.py').is_file()
    assert (ROOT/'core/adaptive_resources.py').is_file()
    builder = (ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
    assert f'v{VERSION}-build-gated-ui' in builder
    assert 'npm run build' in builder
