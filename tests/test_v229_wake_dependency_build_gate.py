"""Regression for Windows build gate and NumPy missing from test environment."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def test_numpy_is_in_desktop_and_test_requirements():
    for name in ('requirements-desktop.txt', 'requirements-test.txt'):
        requirements = (ROOT / name).read_text(encoding='utf-8')
        assert 'numpy==2.2.6' in requirements, name


def test_windows_install_before_acoustic_pytest_gate():
    content = (ROOT / 'scripts/build_windows.ps1').read_text(encoding='utf-8')
    install = content.index("-r requirements-desktop.txt")
    verify = content.index("'Verifying direct microphone runtime into BARQ desktop before Python tests'")
    test = content.index('Running project unit and API tests')
    package = content.index('Packaging native Windows .exe')
    assert install < verify < test < package
    assert 'verify_voice_build_dependencies.py' in content
    assert "--collect-all', 'numpy'" in content


def test_wheel_preparation_is_part_of_update_kit_and_uses_sha256():
    script = (ROOT / 'scripts/build_barq_update_kit.ps1').read_text(encoding='utf-8')
    assert script.index('prepare_voice_wheels.py') < script.index('(Join-Path $root \'scripts\\build_short_path.py\') --source')
    download = (ROOT / 'scripts/prepare_voice_wheels.py').read_text(encoding='utf-8')
    assert 'numpy-2.2.6-cp311-cp311-win_amd64.whl' in download
    assert 'e8213002e427c69c45a52bbd94163084025f533a55a59d6f9c5b820774ef3303' in download
    assert 'hashlib.sha256' in download
    assert '--no-deps' in download


def test_voice_dependency_checker_invokes_real_fingerprint():
    content = (ROOT / 'scripts/verify_voice_build_dependencies.py').read_text(encoding='utf-8')
    assert 'signature(pcm)' in content
    assert '(36, 13)' in content
