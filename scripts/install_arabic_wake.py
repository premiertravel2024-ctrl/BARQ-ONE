"""Explicit installer for the OFFLINE Vosk Arabic speech recognizer (318 MB)."""
from __future__ import annotations
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request
import os

NAME='vosk-model-ar-mgb2-0.4'
URL='https://alphacephei.com/vosk/models/'+NAME+'.zip'
# Installed EXE keeps downloaded model visibly under the chosen BARQ install
# directory. Source checkout installs to its own models/wake folder.
import sys
_APP=(Path(sys.executable).resolve().parent if getattr(sys,'frozen',False)
      else Path(__file__).resolve().parents[1])
DEST=Path(os.getenv('BARQ_WAKE_MODEL_DIR',str(_APP/'models'/'wake'))).expanduser()



def install(archive_path: str | Path | None = None):
    target=DEST/NAME
    if (target/'am').is_dir() and (target/'conf').is_dir():
        print('Arabic wake model is already installed:',target)
        return
    DEST.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='barq-wake-',dir=DEST) as temp:
        folder=Path(temp)
        archive=folder/'model.zip'
        if archive_path is not None:
            supplied=Path(archive_path).resolve(strict=True)
            if not supplied.is_file():
                raise ValueError('Arabic wake model archive not found')
            if supplied.stat().st_size > 900*1024*1024:
                raise ValueError('Model archive exceeded size limit')
            shutil.copyfile(supplied,archive)
        else:
            print('Downloading official offline Arabic Vosk model (~318 MB):',URL,flush=True)
            req=Request(URL,headers={'User-Agent':'BARQ offline wake setup/1.0'})
            with urlopen(req,timeout=90) as stream,archive.open('wb') as dest:
                size=0
                while True:
                    chunk=stream.read(1024*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>900*1024*1024:raise ValueError('Model archive exceeded size limit')
                    dest.write(chunk)
                    if size%(25*1024*1024)<len(chunk):print('Downloaded',size//(1024*1024),'MB',flush=True)
        with zipfile.ZipFile(archive) as z:
            bad=z.testzip()
            if bad:raise ValueError('Corrupted archive file: '+bad)
            total_uncompressed=0
            for item in z.infolist():
                parts=Path(item.filename).parts
                total_uncompressed+=item.file_size
                if total_uncompressed>6*1024*1024*1024:
                    raise ValueError('Uncompressed model exceeded safety limit')
                if not parts or parts[0]!=NAME or '..' in parts or item.is_dir() and item.file_size:
                    raise ValueError('Unexpected archive path')
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symlinks are not accepted')
            z.extractall(folder/'extracted')
        unpacked=folder/'extracted'/NAME
        if not (unpacked/'am').is_dir() or not (unpacked/'conf').is_dir():raise ValueError('Incomplete Vosk model')
        if target.exists():raise ValueError('Target already exists; remove incomplete model manually first')
        shutil.move(str(unpacked),str(target))
    print('Arabic wake model installed at:',target)
    print('No microphone audio is sent to the model download server.')


if __name__=='__main__':install()
