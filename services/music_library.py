"""Persistent local music library. Only native picker selections may enter it."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
from core.paths import data_dir

_lock=threading.RLock()
EXTENSIONS={'.mp3','.m4a','.mp4','.aac','.flac','.ogg','.opus','.wav'}

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
