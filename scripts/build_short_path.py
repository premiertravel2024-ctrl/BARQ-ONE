"""Stage Windows builds in a short, fresh directory without registry changes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

EXCLUDED_DIRS = {'node_modules', '.buildvenv', '.venv', 'venv', '.git',
                 '__pycache__', '.pytest_cache', 'dist', 'release', '.build-state'}


def ignore_build_files(directory, names):
    """Do not copy partially installed environments, outputs, or local secrets."""
    skipped=[]
    for name in names:
        path=Path(directory)/name
        if path.is_symlink() or (path.is_dir() and name in EXCLUDED_DIRS):
            skipped.append(name)
        elif name == '.env' or name.startswith('.env.') and name != '.env.example':
            skipped.append(name)
        elif path.suffix.lower() in {'.pyc', '.sqlite', '.sqlite3', '.log'}:
            skipped.append(name)
    return skipped


def version_for(source):
    manifest=(source/'scripts'/'installer.iss').read_text(encoding='utf-8-sig')
    match=re.search(r'^#define AppVersion "([0-9]+(?:\.[0-9]+){1,3})"',manifest,re.M)
    if not match:
        raise ValueError('Cannot read the installer version from scripts/installer.iss')
    return match.group(1)


def build_base():
    custom=os.environ.get('BARQ_BUILD_BASE')
    local=os.environ.get('LOCALAPPDATA')
    if custom:
        return Path(custom).expanduser().resolve()
    if not local:
        raise ValueError('LOCALAPPDATA is missing. Set BARQ_BUILD_BASE to a writable short folder.')
    return (Path(local)/'Bq'/'b').resolve()


def validate_build_base(base, *, windows=None):
    # Check the Windows budget without creating a too-long directory. The extra
    # ten characters account for the separator and mkdtemp's generated name.
    if windows is None:
        windows=os.name == 'nt'
    if windows and len(str(base))+10 > 80:
        raise ValueError('Build path is too long. Set BARQ_BUILD_BASE to a writable short folder, e.g. C:\\BQ-build.')


def run_build(source, base, runner=None, *, bundled_ui=False):
    source=Path(source).resolve()
    base=Path(base).resolve()
    if base==source or source in base.parents:
        raise ValueError('Build staging folder must be outside the source tree')
    validate_build_base(base)
    version=version_for(source)
    marker_name=f'recovery-v{version}.marker' if bundled_ui else f'build-ok-v{version}.marker'
    setup_name=f'BARQ_Setup_{version}.exe'
    destination=source/'release'/'recovery' if bundled_ui else source/'release'
    # A previous build must never be reported as a successful new build.
    (destination/marker_name).unlink(missing_ok=True)
    (destination/'BARQ_BUILD_FAILURE.txt').unlink(missing_ok=True)
    base.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='b',dir=base))
    print(f'Building in short folder: {stage}',flush=True)
    shutil.copytree(source,stage,dirs_exist_ok=True,ignore=ignore_build_files)
    # Every new build MUST use the same API file as the selected source folder.
    source_api = source / 'api.py'
    stage_api = stage / 'api.py'
    # Minimal synthetic source fixtures do not include api.py. Production
    # builds still verify its presence from build_windows.ps1 before npm.
    if source_api.is_file() != stage_api.is_file():
        raise RuntimeError('BARQ api.py differs between source and staged build')
    print(f'[BARQ SOURCE] Selected project: {source}', flush=True)
    print(f'[BARQ SOURCE] Staged project: {stage}', flush=True)
    if source_api.is_file():
        source_sha = hashlib.sha256(source_api.read_bytes()).hexdigest()
        stage_sha = hashlib.sha256(stage_api.read_bytes()).hexdigest()
        print(f'[BARQ SOURCE] api.py sha256 source={source_sha} stage={stage_sha}',flush=True)
        if source_sha != stage_sha:
            raise RuntimeError('Staged FastAPI source differs from the selected project; build blocked')
    command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
             '-File',str(stage/'scripts'/'build_windows.ps1')]
    if bundled_ui: command.append('-UseBundledUI')
    command.append('-StagedBuild')
    result=(runner or subprocess.run)(command,cwd=str(stage),check=False)
    if result.returncode:
        destination.mkdir(parents=True,exist_ok=True)
        if (stage/'release').is_dir():
            for log in (stage/'release').iterdir():
                # Copy every pytest diagnostic, especially the failures summary.
                # Previous releases copied *.log but dropped *-failures.txt.
                if log.is_file() and (log.suffix in ('.log', '.xml', '.json')
                                      or log.name.startswith('python-tests')
                                      or log.name.startswith('python-venv-')
                                      or log.name.startswith('dependency-')
                                      or log.name.startswith('installer-smoke')
                                      or log.name == 'BARQ_BUILD_FAILURE.txt'):
                    shutil.copy2(log, destination / log.name)
            # A user should not have to dig through a temporary AppData folder
            # or send one screenshot for each independent failure.
            with zipfile.ZipFile(destination / 'BARQ_DIAGNOSTICS.zip', 'w',
                                 compression=zipfile.ZIP_DEFLATED) as archive:
                for diagnostic in destination.iterdir():
                    if diagnostic.is_file() and (diagnostic.name.startswith('python-venv-')
                                                 or diagnostic.name.startswith('python-tests')
                                                 or diagnostic.name.startswith('installer-smoke')
                                                 or diagnostic.name.startswith('dependency-')
                                                 or diagnostic.name == 'windows-build.log'):
                        archive.write(diagnostic, arcname=diagnostic.name)
        (destination/'BARQ_BUILD_FAILURE.txt').write_text(
            f'BARQ update build failed (exit {result.returncode}).\n'
            f'Full temporary build folder: {stage}\n'
            f'Logs and test results copied to: {destination}\n'
            'The installed BARQ and voice model are unchanged.\n',
            encoding='utf-8')
        raise RuntimeError(f'Windows build failed (exit {result.returncode}). Files and logs remain at: {stage}')
    release=stage/'release'
    marker=release/marker_name
    setup=release/setup_name
    if not setup.is_file() or not marker.is_file():
        raise RuntimeError(f'Build did not produce a verified installer. Inspect: {stage}')
    marker_text=marker.read_text(encoding='utf-8-sig').strip()
    if not marker_text.startswith(f'ok|BARQ|{version}|'):
        raise RuntimeError('Build completion marker is invalid')
    report=json.loads((release/'self-test.json').read_text(encoding='utf-8-sig'))
    if report.get('status')!='ok' or report.get('ui')!='react' or report.get('frozen') is not True:
        raise RuntimeError('Packaged executable validation did not pass')
    portable=stage/'dist'/'BARQ'/'BARQ.exe'
    if not portable.is_file():
        raise RuntimeError('Verified build is missing the portable executable')
    if not (release/f'BARQ_Portable_{version}.zip').is_file():
        shutil.make_archive(str(release/f'BARQ_Portable_{version}'),'zip',
                            root_dir=stage/'dist',base_dir='BARQ')
    destination.mkdir(parents=True,exist_ok=True)
    for artifact in release.iterdir():
        if artifact.is_file() and artifact.name!=marker_name:
            shutil.copy2(artifact,destination/artifact.name)
    # Copy the completion marker LAST, only after all output transfers succeeded.
    shutil.copy2(marker,destination/marker_name)
    print(f'Windows Setup: {destination/setup_name}',flush=True)
    print(f'Portable app ZIP: {destination / f"BARQ_Portable_{version}.zip"}',flush=True)
    return destination/setup_name


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--bundled-ui',action='store_true',help='Use the verified bundled React UI instead of rebuilding TypeScript')
    args=parser.parse_args(argv)
    try:
        run_build(args.source,build_base(),bundled_ui=args.bundled_ui)
    except (OSError,ValueError,RuntimeError) as exc:
        print(f'BUILD FAILED: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
