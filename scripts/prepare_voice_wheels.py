"""Download and hash-check the official NumPy Windows wheel to this update kit.

Designed to run on Windows Python 3.11 (x64) *before* the staged build.
Does not touch the installed application or any global Python packages.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

WHEEL = 'numpy-2.2.6-cp311-cp311-win_amd64.whl'
SHA256 = 'e8213002e427c69c45a52bbd94163084025f533a55a59d6f9c5b820774ef3303'
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'vendor' / 'windows-wheels'


def valid(path: Path) -> bool:
    if not path.is_file():
        return False
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest() == SHA256


def main() -> int:
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 11) or sys.maxsize < 2**32:
        print('Windows Python 3.11 x64 required for Windows NumPy wheel cache', file=sys.stderr)
        return 2
    DEST.mkdir(parents=True, exist_ok=True)
    wheel = DEST / WHEEL
    if valid(wheel):
        print(f'Official NumPy Windows wheel is cached and hash-verified: {wheel}')
        return 0
    if wheel.exists():
        wheel.unlink()  # Never trust a corrupt/partial wheel.
    print('Downloading official NumPy 2.2.6 wheel from PyPI into the BARQ update kit...')
    command = [sys.executable, '-m', 'pip', 'download', '--disable-pip-version-check',
               '--only-binary=:all:', '--no-deps', '--retries', '5', '--timeout', '60',
               '--dest', str(DEST), 'numpy==2.2.6']
    result = subprocess.run(command, check=False)
    if result.returncode != 0 or not valid(wheel):
        print('NumPy download failed or checksum mismatch. Check internet/PyPI access. '
              'Existing BARQ installation was not changed.', file=sys.stderr)
        if wheel.exists():
            wheel.unlink()
        return 1
    print(f'Download verified and saved beside the BARQ source: {wheel}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
