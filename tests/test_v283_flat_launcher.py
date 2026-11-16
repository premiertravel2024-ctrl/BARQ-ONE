from core.version import VERSION
"""Regression tests: launcher path confusion under double BARQ_Source folders."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]

def test_flat_archive_has_a_single_source_root():
    assert (ROOT/'BUILD_BARQ.bat').is_file()
    assert (ROOT/'BUILD_WINDOWS_EXE.bat').is_file()
    assert (ROOT/'scripts/build_windows.ps1').is_file()
    assert (ROOT/'frontend/package.json').is_file()
    assert not (ROOT/'BARQ_Source').exists()

def test_launcher_resolves_paths_relative_to_itself_and_checks_prerequisites():
    outer=(ROOT/'BUILD_BARQ.bat').read_text()
    inner=(ROOT/'BUILD_WINDOWS_EXE.bat').read_text()
    assert 'set "ROOT=%~dp0"' in outer
    assert 'set "ENTRY=%~dp0"' in inner
    assert 'if exist "%ENTRY%scripts\\build_windows.ps1"' in inner
    assert 'frontend\\package.json' in inner
    assert 'scripts\\installer.iss' in inner
    assert 'dir /b' in inner
    assert VERSION in inner
    assert re.search(r'powershell\.exe.*-File "%SCRIPT%"',inner)

def test_script_version_matches_staged_builder_and_inno():
    assert f'$version = \'{VERSION}\'' in (ROOT/'scripts/build_windows.ps1').read_text()
    assert f'#define AppVersion "{VERSION}"' in (ROOT/'scripts/installer.iss').read_text()
    assert f'BARQ_Setup_{VERSION}.exe' in (ROOT/'BUILD_BARQ.bat').read_text()
