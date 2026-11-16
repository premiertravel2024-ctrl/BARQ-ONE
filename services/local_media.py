"""Bounded, read-only local media discovery for the user's consented folders.

Never runs media or sends file contents to an external provider. This is a
metadata inventory, NOT an opinion/review or a whole-disk index.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from computer_control.safety.policy import sensitive

EXTENSIONS={'.mkv','.mp4','.avi','.mov','.wmv','.m4v','.webm','.mpg','.mpeg','.ts'}
QUALITY=((r'(?i)(?:^|[. _-])(?:2160p|4k|uhd)(?:[. _-]|$)', '4K', 4),
         (r'(?i)(?:^|[. _-])1440p(?:[. _-]|$)', '1440p', 3),
         (r'(?i)(?:^|[. _-])1080p(?:[. _-]|$)', '1080p', 2),
         (r'(?i)(?:^|[. _-])720p(?:[. _-]|$)', '720p', 1))
_SKIP={'appdata','windows','system32','program files','program files (x86)',
       '.git','node_modules','.venv','venv','__pycache__','$recycle.bin','system volume information'}


def _roots(allowed_folders:list[str], home:Path|None=None)->list[Path]:
    """Only discover ordinary video locations + explicitly allowlisted roots.

    Allowlisted folders are user-controlled through the desktop consent UI.
    Never silently traverse all Windows volumes or network shares.
    """
    home=home or Path.home()
    candidates=[home/'Videos',home/'Movies',home/'Downloads',*(Path(p).expanduser() for p in allowed_folders)]
    roots=[]
    for p in candidates:
        try:
            canonical=p.resolve(strict=True)
            if (not canonical.is_dir() or sensitive(str(canonical)) or
                (os.name=='nt' and str(canonical).startswith('\\\\'))):
                continue
            if canonical not in roots:roots.append(canonical)
        except (OSError,RuntimeError,ValueError):continue
    return roots[:12]


def _display_title(name:str)->str:
    title=Path(name).stem
    title=re.sub(r'(?i)(?:[. _-]+)(?:2160p|1440p|1080p|720p|4k|uhd|bluray|web-dl|webrip|x264|x265|hevc|hdr|aac|dts).*$', '',title)
    return re.sub(r'[._]+',' ',title).strip()[:110] or Path(name).stem[:110]


def _quality(name:str)->tuple[str,int]:
    for pattern,label,rank in QUALITY:
        if re.search(pattern,name):return label,rank
    return 'غير محددة',0


def discover_movies(allowed_folders:list[str]|None=None, *, home:Path|None=None,
                    query:str='', max_results:int=12, max_entries:int=7000,
                    max_seconds:float=2.0, depth_limit:int=6, include_paths:bool=False)->dict:
    """Safely enumerate only media filenames under local, explicitly scoped roots."""
    # An enabled global index may still be starting, stale, or empty immediately
    # after a new movie is copied.  Never return an empty/incomplete index reply
    # as the final result without trying the bounded read-only folder scan.
    # The fallback scans ONLY existing explicitly permitted/default video roots;
    # it never broadens consent to an entire volume.
    if not isinstance(query,str) or len(query)>120:raise ValueError('Invalid search phrase')
    if not isinstance(allowed_folders,(list,type(None))):raise ValueError('Invalid folders')
    if home is None:
        from services import device_index
        if device_index.settings()['enabled']:
            result=device_index.browse_movies(query=query,allowed_folders=allowed_folders or [],limit=max_results,**({'include_paths':True} if include_paths else {}))
            if result.get('status') == 'ok' and result.get('movies'):
                return result
    roots=_roots(allowed_folders or [],home)
    matches=[];scanned=0;truncated=False;deadline=time.monotonic()+max_seconds
    seen_dirs=set()
    for root in roots:
        queue=[(root,0)]
        while queue:
            if scanned>=max_entries or time.monotonic()>deadline:
                truncated=True;break
            folder,depth=queue.pop(0)
            # Do not follow directory aliases, symlinks, mount-point loops or junctions.
            try:
                info=folder.stat(follow_symlinks=False)
                if folder.is_symlink() or (info.st_dev,info.st_ino) in seen_dirs:continue
                seen_dirs.add((info.st_dev,info.st_ino))
                with os.scandir(folder) as listing:
                    for entry in listing:
                        scanned+=1
                        if scanned>=max_entries or time.monotonic()>deadline:
                            truncated=True;break
                        name=entry.name
                        if name.startswith('.') or name.casefold() in _SKIP:continue
                        try:
                            if entry.is_symlink():continue
                            if entry.is_dir(follow_symlinks=False):
                                if depth<depth_limit and not sensitive(entry.path):queue.append((Path(entry.path),depth+1))
                            elif entry.is_file(follow_symlinks=False) and Path(name).suffix.lower() in EXTENSIONS:
                                if query and query.casefold() not in name.casefold():continue
                                stat=entry.stat(follow_symlinks=False)
                                if stat.st_size<2*1024*1024:continue  # exclude most thumbnails and broken files
                                label,qrank=_quality(name)
                                matches.append({'name':_display_title(name),'filename':name[:150],
                                                'quality':label,'size_gb':round(stat.st_size/1e9,2),
                                                'folder':folder.name[:70],
                                                '_path':str(Path(entry.path).resolve()),'_rank':qrank,'_size':stat.st_size})
                        except (OSError,PermissionError):continue
            except (OSError,PermissionError):continue
        if truncated:break
    matches.sort(key=lambda x:(x['_rank'],x['_size']),reverse=True)
    selected=[{k:v for k,v in movie.items() if not k.startswith('_') or (include_paths and k=='_path')} for movie in matches[:max(1,min(max_results,30))]]
    return {'status':'ok','count_found':len(matches),'scanned_entries':scanned,
            'truncated':truncated,'searched_folders':[p.name for p in roots],
            'movies':selected,
            'note':'ترتيب حسب الجودة الظاهرة وملف الفيديو، مش تقييم فني. مفيش أي ملف اتشغّل أو اترفع للإنترنت.'}
