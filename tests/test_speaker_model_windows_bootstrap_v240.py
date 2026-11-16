"""Offline check: local Windows build must prepare verified speaker model before staging."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "E9848563DA86F263117134DFD7AD63C92355B37DE492B55E325400C9D9C39012"


def test_speaker_model_is_bootstrapped_before_short_path_staging():
    source = (ROOT / "scripts/build_windows.ps1").read_text(encoding="utf-8")
    assert source.index("ensure_speaker_model.ps1") < source.index("if (-not $StagedBuild) {")
    assert EXPECTED in source
    assert "Get-FileHash -Algorithm SHA256" in source


def test_speaker_bootstrap_downloads_only_fixed_https_sources_with_sha_pin():
    source = (ROOT / "scripts/ensure_speaker_model.ps1").read_text(encoding="utf-8")
    assert EXPECTED in source
    assert "https://github.com/k2-fsa/sherpa-onnx/releases/download/" in source
    assert "https://huggingface.co/" in source
    assert "Test-VerifiedSpeakerModel $partial" in source
    assert "Move-Item -LiteralPath $partial -Destination $file -Force" in source


def test_downloaded_speaker_weights_are_not_committed():
    ignores = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "models/speaker/*.onnx" in ignores
