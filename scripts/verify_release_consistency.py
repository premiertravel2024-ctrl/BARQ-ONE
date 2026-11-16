"""Preflight that ensures every BARQ release entrypoint agrees before heavy build work."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

def verify():
    errors=[]
    def text(name):
        return (ROOT/name).read_text(encoding='utf-8-sig')
    manifest=text('scripts/installer.iss')
    # Inno rejects its default UsePreviousLanguage=yes with a dynamic AppId.
    # Check the actual [Setup] section so a commented line or another section
    # cannot satisfy the preflight. This runs before npm and PyInstaller.
    setup={}
    section=''
    for line in manifest.splitlines():
        line=line.strip()
        if not line or line.startswith((';','#')):
            continue
        if line.startswith('[') and line.endswith(']'):
            section=line.casefold()
        elif section=='[setup]' and '=' in line:
            key,value=line.split('=',1)
            setup[key.strip().casefold()]=value.strip().casefold()
    if '{code:' in setup.get('appid','') and setup.get('usepreviouslanguage')!='no':
        errors.append('scripts/installer.iss: dynamic AppId requires UsePreviousLanguage=no in [Setup]')
    match=re.search(r'^#define AppVersion "([0-9]+(?:\.[0-9]+){1,3})"',manifest,re.M)
    if not match:
        return ['scripts/installer.iss is missing AppVersion']
    version=match.group(1)
    packages=json.loads(text('frontend/package.json'))
    lock=json.loads(text('frontend/package-lock.json'))
    for key,value in [('frontend/package.json',packages.get('version')),
                      ('frontend/package-lock.json',lock.get('version')),
                      ('frontend/package-lock.json packages.root',lock.get('packages',{}).get('',{}).get('version'))]:
        if value!=version:errors.append(f'{key}: {value!r} differs from {version}')
    expected={
        'core/version.py':[f"VERSION = '{version}'"],
        'scripts/build_windows.ps1':[f"$version = '{version}'",f"v{version}-build-gated-ui"],
        'BUILD_BARQ.bat':[f'BARQ_Setup_{version}.exe',f'build-ok-v{version}.marker'],
        'BUILD_WINDOWS_EXE.bat':[f'set "VERSION={version}"'],
        'frontend/src/components/workspace/WorkspaceStudio.tsx':[f'v{version}-build-gated-ui'],
        '.github/workflows/windows-build.yml':[f'BARQ_Setup_{version}.exe',f'BARQ_Portable_{version}.zip'],
    }
    for file,tokens in expected.items():
        source=text(file)
        for token in tokens:
            if token not in source:errors.append(f'{file}: expected {token}')
    return errors

if __name__=='__main__':
    try:errors=verify()
    except (OSError,ValueError,json.JSONDecodeError) as exc:errors=[f'Preflight failed to parse a release file: {exc}']
    if errors:
        for line in errors:print('BARQ RELEASE PREFLIGHT ERROR: '+line,file=sys.stderr)
        raise SystemExit(1)
    print('BARQ release metadata and frontend lockfile are consistent.')
