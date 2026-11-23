"""Persistent local music library. Only native picker selections may enter it."""
import hashlib
import shutil
import zipfile
from tempfile import NamedTemporaryFile
import json
import os
from pathlib import Path
import secrets
import threading
from core.paths import data_dir

_lock=threading.RLock()
EXTENSIONS={'.mp3','.m4a','.mp4','.aac','.flac','.ogg','.opus','.wav','.webm'}

def folder():
    p=data_dir()/'music';p.mkdir(parents=True,exist_ok=True);return p

def load():
    try:
        obj=json.loads((folder()/'library.json').read_text(encoding='utf-8'))
        return obj if isinstance(obj,dict) else {}
    except (OSError,ValueError):return {}

def save(records):
    tmp=folder()/('library.'+secrets.token_hex(6)+'.tmp')
    try:
        tmp.write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8');os.replace(tmp,folder()/'library.json')
    finally:tmp.unlink(missing_ok=True)

def public(record):return {k:v for k,v in record.items() if k!='path'}

def tracks():
    with _lock:return [public(r) for r in load().values()]

def source(identifier):
    with _lock:r=load().get(identifier)
    if not r:raise ValueError('Track not found')
    p=Path(r['path'])
    if not p.is_file() or p.is_symlink() or p.suffix.lower() not in EXTENSIONS:raise ValueError('File moved or unavailable. Import it again.')
    return p

def metadata(p):
    import mutagen
    identifier=hashlib.sha256(str(p).lower().encode()).hexdigest()[:24]
    record={'id':identifier,'path':str(p),'title':p.stem,'artist':'','album':'','duration':None,'artwork':False}
    try:
        easy=mutagen.File(p,easy=True)
        if easy:
            record['duration']=getattr(easy.info,'length',None)
            for field in ('title','artist','album'):
                value=easy.get(field)
                if value:record[field]=str(value[0])[:300]
        raw=mutagen.File(p)
        if raw and raw.tags:
            for field, tag in (('title','TIT2'),('artist','TPE1'),('album','TALB')):
                frame=raw.tags.get(tag)
                if frame is not None and getattr(frame,'text',None):record[field]=str(frame.text[0])[:300]
        picture=None
        if getattr(raw,'pictures',None):picture=raw.pictures[0].data
        elif raw and raw.tags:
            if hasattr(raw.tags,'getall'):
                images=raw.tags.getall('APIC')
                if images:picture=images[0].data
            if not picture and raw.tags.get('covr'):picture=bytes(raw.tags['covr'][0])
        if picture and len(picture)<=5*1024*1024:
            # Only actual JPEG/PNG covers may be served as images.
            ext='.jpg' if picture.startswith(b'\xff\xd8\xff') else '.png' if picture.startswith(b'\x89PNG\r\n\x1a\n') else None
            if ext:
                (folder()/(identifier+ext)).write_bytes(picture);record['artwork']=True
    except (OSError,ValueError,mutagen.MutagenError):pass
    return record

def import_selected(paths):
    imported=[];skipped=0
    with _lock:
        records=load()
        for value in paths:
            p=Path(value)
            if p.suffix.lower() not in EXTENSIONS or p.is_symlink() or not p.is_file():skipped+=1;continue
            try:
                r=metadata(p.resolve(strict=True));records[r['id']]=r;imported.append(public(r))
            except (OSError,ValueError):skipped+=1
        save(records)
    return {'imported':imported,'skipped':skipped,'tracks':tracks()}


# User-provided collection; large source audio is deliberately not checked into Git.
# The Windows file picker imports WINTER MUSIC.zip into the app's OWN persistent
# music folder, so moving the downloaded ZIP cannot break playback.
WINTER_COLLECTION="WINTER MUSIC"
WINTER_TRACKS=(
    ("WINTER MUSIC 01.webm", 7288.768),
    ("WINTER MUSIC 02.m4a", 3600.649),
    ("WINTER MUSIC 03.m4a", 7555.913),
)
WINTER_MAX_TRACK=190*1024*1024
WINTER_MAX_TOTAL=420*1024*1024


def _winter_signature(name: str, first: bytes) -> bool:
    if name.endswith(".webm"):
        return first.startswith(b"\x1a\x45\xdf\xa3")
    if name.endswith(".m4a"):
        return len(first)>=12 and first[4:8]==b"ftyp"
    return False


def import_winter_pack(zip_path: str | Path):
    """Import exactly the 3 named owner-provided recordings (no zip-slip, no re-encoding).

    Extract into app-private persistent music storage and publish index entries
    only after every file is verified. Reimports are idempotent.
    """
    archive=Path(zip_path)
    if not archive.is_file() or archive.suffix.lower()!=".zip":
        raise ValueError("Select a WINTER MUSIC ZIP file")
    if archive.stat().st_size>WINTER_MAX_TOTAL:
        raise ValueError("WINTER MUSIC ZIP is too large")
    destination=folder()/WINTER_COLLECTION
    with _lock:
        destination.mkdir(parents=True,exist_ok=True)
        staged=[]
        try:
            with zipfile.ZipFile(archive,"r",allowZip64=True) as packed:
                infos=[]
                for name,_ in WINTER_TRACKS:
                    matches=[item for item in packed.infolist()
                             if item.filename in (name,WINTER_COLLECTION+"/"+name)]
                    if len(matches)!=1:
                        raise ValueError("WINTER MUSIC pack must contain all three distinct tracks")
                    info=matches[0]
                    if info.is_dir() or info.file_size<32 or info.file_size>WINTER_MAX_TRACK:
                        raise ValueError("Invalid WINTER MUSIC audio file size")
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("Archive links are not accepted")
                    infos.append((name,info))
                if sum(info.file_size for _,info in infos)>WINTER_MAX_TOTAL:
                    raise ValueError("WINTER MUSIC pack is too large")
                for name,info in infos:
                    with NamedTemporaryFile(dir=destination,prefix=".barq-winter-",suffix=".part",delete=False) as target:
                        temp=Path(target.name)
                        staged.append((name, temp))
                        total=0
                        first=b""
                        with packed.open(info,"r") as original:
                            while True:
                                chunk=original.read(128*1024)
                                if not chunk:break
                                if total==0:first=chunk[:16]
                                total+=len(chunk)
                                if total>info.file_size or total>WINTER_MAX_TRACK:
                                    raise ValueError("WINTER MUSIC audio exceeded expected size")
                                target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                        if total!=info.file_size or not _winter_signature(name,first):
                            raise ValueError("WINTER MUSIC audio file is corrupt or mislabeled")
                records=load()
                updated=[]
                for (name,duration),(_,temp) in zip(WINTER_TRACKS,staged):
                    path=destination/name
                    if path.is_symlink():
                        raise ValueError("Symlink destination is not allowed")
                    # A persistent copy belongs to BARQ, not the removable ZIP.
                    os.replace(temp,path)
                    identifier=hashlib.sha256(str(path).lower().encode()).hexdigest()[:24]
                    record={"id":identifier,"path":str(path),"title":Path(name).stem,
                            "artist":"","album":WINTER_COLLECTION,
                            "duration":duration,"artwork":False}
                    records[identifier]=record
                    updated.append(public(record))
                save(records)
                return {"collection":WINTER_COLLECTION,"imported":updated,
                        "tracks":[public(record) for record in records.values()]}
        except (zipfile.BadZipFile,EOFError) as exc:
            raise ValueError("Invalid or incomplete WINTER MUSIC ZIP") from exc
        finally:
            for _,temp in staged:
                temp.unlink(missing_ok=True)
