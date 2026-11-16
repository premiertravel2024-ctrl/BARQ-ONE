"""Verify and hash newly built release outputs. Does not manufacture Windows evidence."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.version import VERSION


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def verify(root=ROOT,version=VERSION):
    release=root/'release'
    setup=release/f'BARQ_Setup_{version}.exe'
    portable=release/f'BARQ_Portable_{version}.zip'
    executable=root/'dist/BARQ/BARQ.exe'
    for path in (setup,executable):
        if not path.is_file() or path.stat().st_size<2 or path.read_bytes()[:2]!=b'MZ':
            raise ValueError(f'Missing or invalid Windows executable: {path.name}')
    reports=[]
    for name in ('self-test.json','installed-self-test.json'):
        data=json.loads((release/name).read_text(encoding='utf-8-sig'))
        if data.get('status')!='ok' or data.get('frozen') is not True or data.get('version')!=version or data.get('ui')!='react' or data.get('cleanup_completed') is not True:
            raise ValueError('Executable smoke report failed: '+name)
        reports.append(name)
    with zipfile.ZipFile(portable) as archive:
        if archive.read('BARQ/BARQ.exe')!=executable.read_bytes():
            raise ValueError('Portable archive differs from tested executable')
        if archive.testzip():raise ValueError('Portable archive CRC failure')
    paths=(setup,portable,executable,*(release/name for name in reports))
    evidence={'version':version,'platform':'windows-x64','smoke_reports':reports,
              'sha256':{str(path.relative_to(root)).replace('\\','/'):sha256(path) for path in paths}}
    (release/'release-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return evidence


if __name__=='__main__':
    try:
        verify()
        print('Release outputs match tested executables and installer smoke reports.')
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
        print('BARQ release verification failed: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
