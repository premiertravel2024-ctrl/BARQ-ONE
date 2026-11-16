"""Exercise staging, output validation, and recovery without claiming a Windows build."""
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import build_short_path as build


@pytest.fixture
def short_paths(tmp_path, monkeypatch):
    # pytest's default Windows temp path includes the long test function name.
    # Use the same short base as the real builder; keep all test data compact.
    base=build.build_base() if os.name == 'nt' else tmp_path
    build.validate_build_base(base)
    base.mkdir(parents=True,exist_ok=True)
    allocated=[]
    original_mkdtemp=tempfile.mkdtemp
    with tempfile.TemporaryDirectory(prefix='t',dir=base) as directory:
        def tracked_mkdtemp(*args,**kwargs):
            stage=original_mkdtemp(*args,**kwargs)
            allocated.append(Path(stage))
            return stage
        monkeypatch.setattr(build.tempfile,'mkdtemp',tracked_mkdtemp)
        try:
            yield Path(directory),base
        finally:
            for stage in allocated:
                    try:
                        shutil.rmtree(stage)
                    except FileNotFoundError:
                        # Successful builds reclaim their own stage.
                        pass


def source_tree(parent):
    source=parent/'src'
    (source/'scripts').mkdir(parents=True)
    (source/'scripts/installer.iss').write_text('#define AppVersion "2.5.3"\n')
    (source/'scripts/build_windows.ps1').write_text('param([switch]$StagedBuild)')
    (source/'build').mkdir();(source/'build/jobs.py').write_text('# real source module')
    (source/'.buildvenv/deep').mkdir(parents=True)
    (source/'.buildvenv/deep/partial-install.txt').write_text('broken install')
    (source/'frontend/node_modules/pkg').mkdir(parents=True)
    (source/'frontend/node_modules/pkg/old.js').write_text('old')
    (source/'.env').write_text('TEST_SECRET=do-not-stage')
    (source/'.env.example').write_text('TEST_SECRET=')
    (source/'release').mkdir()
    (source/'release/BARQ_Setup_2.5.3.exe').write_bytes(b'previous installer')
    (source/'release/build-ok-v2.5.3.marker').write_text('old completion')
    return source


def produce_artifacts(stage, valid=True):
    portable=stage/'dist'/'BARQ';portable.mkdir(parents=True)
    (portable/'BARQ.exe').write_bytes(b'simulated portable executable')
    release=stage/'release';release.mkdir()
    (release/'BARQ_Setup_2.5.3.exe').write_bytes(b'new simulated installer')
    (release/'build-ok-v2.5.3.marker').write_text('ok|BARQ|2.5.3|test')
    (release/'self-test.json').write_text(json.dumps({'status':'ok' if valid else 'error','frozen':True,'ui':'react'}))


def test_staging_uses_fresh_snapshot_and_copies_verified_outputs(short_paths):
    parent,base=short_paths
    stages = []
    source=source_tree(parent)
    def runner(command,cwd,check):
        stage=Path(cwd)
        stages.append(stage)
        assert stage!=source
        assert command[-1]=='-StagedBuild'
        assert not (stage/'.buildvenv').exists()
        assert not (stage/'frontend/node_modules').exists()
        assert not (stage/'.env').exists()
        assert (stage/'.env.example').exists()
        assert (stage/'build/jobs.py').is_file()
        assert not (stage/'release').exists()
        produce_artifacts(stage)
        return SimpleNamespace(returncode=0)
    output=build.run_build(source,base,runner=runner)
    assert len(stages) == 1
    assert not stages[0].exists()
    assert output.read_bytes()==b'new simulated installer'
    import zipfile
    with zipfile.ZipFile(source/'release/BARQ_Portable_2.5.3.zip') as archive:
        assert archive.read('BARQ/BARQ.exe')==b'simulated portable executable'
    assert (source/'release/build-ok-v2.5.3.marker').read_text().startswith('ok|BARQ|')
    assert (source/'.buildvenv/deep/partial-install.txt').exists()


def test_failed_build_does_not_claim_previous_installer_as_success(short_paths):
    parent,base=short_paths
    source=source_tree(parent)
    with pytest.raises(RuntimeError,match='exit 1'):
        build.run_build(source,base,runner=lambda *a,**k:SimpleNamespace(returncode=1))
    assert (source/'release/BARQ_Setup_2.5.3.exe').read_bytes()==b'previous installer'
    assert not (source/'release/build-ok-v2.5.3.marker').exists()


@pytest.mark.parametrize('valid',[True,False])
def test_missing_or_invalid_validation_blocks_output_copy(short_paths,valid):
    parent,base=short_paths
    source=source_tree(parent)
    def runner(command,cwd,check):
        stage=Path(cwd)
        if not valid:produce_artifacts(stage,valid=False)
        return SimpleNamespace(returncode=0)
    with pytest.raises(RuntimeError):
        build.run_build(source,base,runner=runner)
    assert (source/'release/BARQ_Setup_2.5.3.exe').read_bytes()==b'previous installer'
    assert not (source/'release/build-ok-v2.5.3.marker').exists()


def test_staging_inside_source_is_rejected(short_paths):
    parent,base=short_paths
    source=source_tree(parent)
    with pytest.raises(ValueError,match='outside the source'):
        build.run_build(source,source/'staging')


def test_main_launcher_and_installer_versions_match():
    root=Path(__file__).resolve().parents[1]
    launcher=root/'BUILD_BARQ.bat' if (root/'BUILD_BARQ.bat').exists() else root.parent/'BUILD_BARQ.bat'
    if not launcher.exists():pytest.skip('Outer ZIP launcher is not part of standalone repository checkout')
    version=build.version_for(root)
    text=launcher.read_text()
    assert f'BARQ_Setup_{version}.exe' in text
    assert f'build-ok-v{version}.marker' in text


def test_windows_path_budget_is_checked_without_creating_long_paths():
    from pathlib import PureWindowsPath
    short=PureWindowsPath(r'C:\Users\Example\AppData\Local\Bq\b')
    build.validate_build_base(short,windows=True)
    build.validate_build_base('a'*70,windows=True)
    with pytest.raises(ValueError,match='too long'):
        build.validate_build_base('a'*71,windows=True)
    original=PureWindowsPath(r'C:\Users\Example\Downloads')/('BARQ_'+'nested_'*18)/'BARQ_Source'
    with pytest.raises(ValueError,match='too long'):
        build.validate_build_base(original,windows=True)
    lxml_tail=PureWindowsPath(r'.buildvenv\Lib\site-packages\lxml\isoschematron\resources\xsl\iso-schematron-xslt1\iso_schematron_skeleton_for_xslt1.xsl')
    assert len(str(original/lxml_tail))>=260
    assert len(str(short/'b12345678'/lxml_tail))<260


def test_failed_build_exports_all_python_failures_in_one_diagnostics_zip(short_paths):
    """Windows users must get full diagnostics in SOURCE/release, not only AppData."""
    import zipfile
    parent, base = short_paths
    source = source_tree(parent)

    def runner(command, cwd, check):
        release = Path(cwd) / 'release'
        release.mkdir()
        (release / 'python-tests.log').write_text('FAILED tests/test_example.py::test_failure\n')
        (release / 'python-tests-failures.txt').write_text('tests/test_example.py::test_failure\n')
        (release / 'python-tests-last-test.txt').write_text('tests/test_example.py::test_failure\n')
        (release / 'windows-build.log').write_text('Build failed after unit tests\n')
        (release / 'installer-smoke.log').write_text('Error 5: access denied to target file\n')
        (release / 'installer-smoke-diagnostics.txt').write_text('Inno exit 5: access denied\n')
        (release / 'installer-smoke-result.json').write_text('{"status": "failed"}')
        return SimpleNamespace(returncode=1)

    with pytest.raises(RuntimeError, match='exit 1'):
        build.run_build(source, base, runner=runner)
    diagnostics = source / 'release' / 'BARQ_DIAGNOSTICS.zip'
    assert diagnostics.is_file()
    with zipfile.ZipFile(diagnostics) as archive:
        assert 'python-tests-failures.txt' in archive.namelist()
        assert 'python-tests.log' in archive.namelist()
        assert 'windows-build.log' in archive.namelist()
        assert 'installer-smoke.log' in archive.namelist()
        assert 'installer-smoke-diagnostics.txt' in archive.namelist()
        assert 'installer-smoke-result.json' in archive.namelist()
        assert b'access denied' in archive.read('installer-smoke-diagnostics.txt')
        assert b'test_failure' in archive.read('python-tests-failures.txt')
    assert not (source / 'release' / 'build-ok-v2.5.3.marker').exists()
