from core.version import VERSION
"""Static regression tests for the BARQ Windows installer failure seen in v2.8.1.

These checks do NOT claim that a Windows EXE has been built on Linux.
"""
from pathlib import Path
import json

from scripts.build_short_path import version_for


ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_version_is_consistent_across_setup_build_ci_frontend_and_launchers():
    version = version_for(ROOT)
    assert version == VERSION
    installer = _read('scripts/installer.iss')
    ps1 = _read('scripts/build_windows.ps1')
    bat = _read('BUILD_WINDOWS_EXE.bat')
    workflow = _read('.github/workflows/windows-build.yml')
    outer = (ROOT / 'BUILD_BARQ.bat').read_text(encoding='utf-8')
    manifest = json.loads(_read('frontend/package.json'))
    lock = json.loads(_read('frontend/package-lock.json'))
    assert manifest['version'] == lock['version'] == lock['packages']['']['version'] == version
    assert f'BARQ_Setup_{version}.exe' in workflow and f'BARQ_Portable_{version}.zip' in workflow
    assert f'BARQ_Setup_{version}.exe' in outer and f'build-ok-v{version}.marker' in outer
    assert f'set "VERSION={version}"' in bat
    assert f"$version = '{version}'" in ps1
    assert 'OutputBaseFilename=BARQ_Setup_{#AppVersion}' in installer


def test_inno_only_compiles_a_built_executable_not_an_empty_dist_folder():
    installer = _read('scripts/installer.iss')
    assert 'AddBackslash(SourcePath)' in installer
    assert '#if !FileExists(BinaryDir + "\\BARQ.exe")' in installer
    assert '#error' in installer and 'BUILD_BARQ.bat' in installer
    assert 'Source: "{#BinaryDir}\\*"' in installer
    assert "Result := '{9BB70D04-1EC5-4BC6-B811-64B08F5C8977}'" in installer


def test_build_pipeline_preflights_inno_and_never_installs_stale_output():
    ps1 = _read('scripts/build_windows.ps1')
    bat = _read('BUILD_WINDOWS_EXE.bat')
    assert ps1.index(f"$version = '{VERSION}'") < ps1.index('$oldSetup =')
    assert ps1.index("find_inno.ps1") < ps1.index('npm ci')
    assert ps1.index('PyInstaller') < ps1.index("$exe = Join-Path")
    assert 'incomplete BARQ directory' in ps1
    assert 'Start-Process -FilePath $exe' in ps1 and '-Wait -PassThru' in ps1
    assert 'Invoke-Step \'Building Windows Setup.exe (Inno Setup)\'' in ps1
    assert 'Join-Path $root \'scripts\\installer.iss\'' in ps1
    assert 'if errorlevel 1' in bat and 'pause' in bat
    assert 'build-ok-v%VERSION%.marker' in bat
    assert 'BARQ_Setup_%VERSION%.exe' in bat
