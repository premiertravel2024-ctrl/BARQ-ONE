"""Consent-gated, local file discovery with optional Everything CLI acceleration.

Never transmits file contents. A background SQLite index covers ordinary files on
explicitly enabled local volumes or user-allowlisted folders. Sensitive/system
paths and Windows reparse points are excluded even in all-drive mode.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from contextlib import closing
from pathlib import Path
from typing import Any

from core.paths import state_file
from computer_control.safety.policy import sensitive, contained

_SKIP_DIRS={'.git','node_modules','__pycache__','.venv','venv','windows','system32',
    'program files','program files (x86)','$recycle.bin','system volume information',
    'recovery','windowsapps','programdata','appdata','.ssh','.aws','.config','.gnupg','.kube'}
_SKIP_NAMES={'pagefile.sys','swapfile.sys','hiberfil.sys','ntuser.dat','sam','security','device_index_settings.json','device_index.sqlite3','device_index.sqlite3-wal','device_index.sqlite3-shm','device_content_index.sqlite3','device_content_index.sqlite3-wal','device_content_index.sqlite3-shm'}
_MAX_REPLY=40
_lock=threading.RLock()
_worker:threading.Thread|None=None
_cancel=threading.Event()
_progress:dict[str,Any]={'status':'idle','entries':0,'folders':0,'started':None,'completed':None,'error':''}


def settings()->dict:
    try:
        cfg=json.loads(state_file('device_index_settings.json').read_text(encoding='utf-8'))
        return {'enabled':cfg.get('enabled') is True,
                'all_local_drives':cfg.get('all_local_drives') is True,
                'content_enabled':cfg.get('content_enabled') is True and cfg.get('enabled') is True}
    except (OSError,ValueError,TypeError):
        return {'enabled':False,'all_local_drives':False,'content_enabled':False}


def configure(*,enabled:bool,all_local_drives:bool=False,content_enabled:bool=False)->dict:
    if not isinstance(content_enabled,bool) or not isinstance(enabled,bool) or not isinstance(all_local_drives,bool):
        raise ValueError('Invalid index settings')
    cfg={'enabled':enabled,'all_local_drives':all_local_drives if enabled else False,
         'content_enabled':content_enabled if enabled else False}
    path=state_file('device_index_settings.json')
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(cfg),encoding='utf-8')
    temp.replace(path)
    if not enabled:
        _cancel.set()
    if not cfg['content_enabled']:
        from services import content_index
        content_index.disable()
        # A disabled index must not retain a searchable inventory on disk.
        # Do not unlink an active SQLite database while the indexer is writing.
    return cfg


def _fixed_drives()->list[Path]:
    if sys.platform!='win32':return []
    try:
        size=ctypes.windll.kernel32.GetLogicalDriveStringsW(0,None)
        buf=ctypes.create_unicode_buffer(size+1)
        ctypes.windll.kernel32.GetLogicalDriveStringsW(size,buf)
        drives=[Path(p) for p in buf[:].split('\0') if p]
        return [p for p in drives if ctypes.windll.kernel32.GetDriveTypeW(str(p))==3]
    except (AttributeError,OSError,ValueError):return []


def scan_roots(cfg:dict,allowed_folders:list[str])->list[Path]:
    if not cfg.get('enabled'):return []
    items=(_fixed_drives() if cfg.get('all_local_drives') else []) + [Path(f).expanduser() for f in allowed_folders]
    out=[]
    for p in items:
        try:
            resolved=p.resolve(strict=True)
            if not resolved.is_dir() or sensitive(str(resolved)) or resolved in out:continue
            if os.name=='nt' and str(resolved).startswith('\\\\'):continue
            out.append(resolved)
        except (ValueError,OSError,RuntimeError):continue
    return out


def _explicit_temp_indices(root: Path) -> frozenset[int]:
    """AppData components explicitly covered by a user-approved Temp root.

    Do not derive consent from TEMP, LOCALAPPDATA or their cached values: in
    Windows builds those can differ from pytest's actual temporary directory.
    Only AppData/Local/Temp triplets already inside the *passed-in root* may
    bypass the metadata crawler's general AppData exclusion. The case-folded
    component check works with real Windows paths and synthetic test paths.
    """
    parts = [part.casefold() for part in root.parts]
    return frozenset(i for i in range(len(parts)-2)
                     if parts[i:i+3] == ['appdata', 'local', 'temp'])


def _windows_temp_root() -> Path | None:
    """Legacy helper retained for backwards-compatible test harnesses.

    The security decision must no longer depend on this environment-derived
    location. Explicit allowlisted roots are evaluated instead.
    """
    if sys.platform != 'win32':
        return None
    try:
        return Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        return None


def _is_explicit_temp_root(root: Path) -> bool:
    return bool(_explicit_temp_indices(root))


def _safe_path(path: Path, *, explicit_root: Path | None = None) -> bool:
    # A user may explicitly allow a Temp workspace even though the broader
    # AppData tree is off limits. Exempt ONLY the AppData components ALREADY
    # present in that exact allowed root. Nested AppData directories remain
    # blocked even when they also spell AppData/Local/Temp.
    exempt = frozenset()
    if explicit_root is not None:
        if not (path == explicit_root or path.is_relative_to(explicit_root)):
            return False
        exempt = _explicit_temp_indices(explicit_root)
    for index, part in enumerate(path.parts):
        name = part.casefold()
        if name in _SKIP_DIRS and not (name == 'appdata' and index in exempt):
            return False
    if (path.name.casefold() in _SKIP_NAMES or path.suffix.lower() in {'.key','.pem','.p12','.pfx'}
        or path.name.casefold().startswith(('.env','id_rsa','id_ed25519')) or sensitive(str(path))):
        return False
    return True


def _safe_path_in_roots(path: Path, roots: list[Path]) -> bool:
    # Fail closed when no approved root contains the candidate. Each root
    # separately determines which specific AppData component, if any, is safe.
    return any(_safe_path(path, explicit_root=root) for root in roots)


def _reparse(entry)->bool:
    try:
        st=entry.stat(follow_symlinks=False)
        return bool(getattr(st,'st_file_attributes',0) & 0x400) or entry.is_symlink()
    except OSError:return True


def _connect():
    db=sqlite3.connect(str(state_file('device_index.sqlite3')),timeout=12)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,name TEXT NOT NULL,extension TEXT,kind TEXT,size INTEGER,modified REAL,generation INTEGER)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_files_name ON files(name COLLATE NOCASE)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)')
        db.commit()
        return db
    except BaseException:
        db.close()
        raise


def _scan(roots:list[Path],stop:threading.Event,*,generation:int|None=None,limit_for_test:int|None=None)->dict:
    """Scan iteratively; no fixed overall file cap in real builds. Cancel safely."""
    gen=generation if generation is not None else int(time.time()*1000)
    found=0;folders=0;errors=0;commits=0
    with closing(_connect()) as db:
        batch=[]
        for root in roots:
            queue=deque([root]);visited=set()
            while queue and not stop.is_set():
                folder=queue.popleft()
                if not _safe_path(folder,explicit_root=root):continue
                try:
                    st=folder.stat(follow_symlinks=False)
                    inode=(st.st_dev,st.st_ino)
                    if inode in visited or getattr(st,'st_file_attributes',0)&0x400:continue
                    visited.add(inode)
                    folders+=1
                    with os.scandir(folder) as directory:
                        for entry in directory:
                            if stop.is_set():break
                            path=Path(entry.path)
                            if not _safe_path(path,explicit_root=root) or _reparse(entry):continue
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    queue.append(path)
                                    stat=entry.stat(follow_symlinks=False)
                                    batch.append((str(path),path.name[:280],'','folder',0,stat.st_mtime,gen))
                                elif entry.is_file(follow_symlinks=False):
                                    stat=entry.stat(follow_symlinks=False)
                                    batch.append((str(path),path.name[:280],path.suffix.lower()[:32],
                                                  'file',stat.st_size,stat.st_mtime,gen))
                                    found+=1
                                    if len(batch)>=250:
                                        db.executemany('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)',batch)
                                        db.commit();commits+=1;batch=[]
                                    if limit_for_test and found>=limit_for_test:
                                        stop.set();break
                            except (PermissionError,OSError):errors+=1
                    if folders%40==0:
                        with _lock:_progress.update(entries=found,folders=folders)
                        time.sleep(.001)  # responsive to stop requests
                except (PermissionError,OSError):errors+=1
        if batch:
            db.executemany('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)',batch);db.commit()
        if not stop.is_set():
            db.execute('DELETE FROM files WHERE generation != ?',(gen,));db.commit()
    return {'status':'cancelled' if stop.is_set() else 'ready','entries':found,'folders':folders,'errors':errors,'commits':commits}


def _run(roots:list[Path]):
    global _progress
    try:
        data=_scan(roots,_cancel)
        with _lock:_progress.update(**data,completed=time.time())
        if data['status']=='ready' and settings().get('content_enabled'):
            from services import content_index
            from computer_control.api import load_policy
            policy=load_policy()
            if policy.enabled:
                content_index.refresh(policy.allowed_folders)
    except (OSError,sqlite3.DatabaseError) as exc:
        with _lock:_progress.update(status='failed',error=type(exc).__name__,completed=time.time())


def refresh(allowed_folders:list[str]):
    global _worker
    cfg=settings()
    if not cfg['enabled']:return {'status':'permission_required','message':'فعّل فهرسة الملفات من إعدادات الكمبيوتر أولًا.'}
    roots=scan_roots(cfg,allowed_folders)
    if not roots:return {'status':'no_roots','message':'لا توجد مجلدات مسموحة وموجودة للفهرسة.'}
    with _lock:
        if _worker and _worker.is_alive():return dict(_progress)
        _cancel.clear()
        _progress.update(status='indexing',entries=0,folders=0,started=time.time(),completed=None,error='')
        _worker=threading.Thread(target=_run,args=(roots,),daemon=True,name='barq-device-indexer')
        _worker.start()
    return status()


def status():
    with _lock:progress=dict(_progress)
    return {'settings':settings(),**progress,'everything_available':bool(shutil.which('es.exe') or shutil.which('es'))}


def _everything_search(query:str,extension:str,limit:int,allowed_roots:list[Path])->list[dict]|None:
    # Everything/ES is OPTIONAL. Never pass user input to a shell.
    binary=shutil.which('es.exe') or shutil.which('es')
    if not binary or sys.platform!='win32':return None
    # ES syntax operators are unsafe/unpredictable from speech. Quote a literal phrase.
    if any(x in query for x in ('"','\r','\n','\0')):return None
    term='"'+query+'"'
    command=[binary,'-n',str(limit*4),'-no-header','-search',term]
    if extension:command+=['-search','ext:'+extension.removeprefix('.')]
    try:
        completed=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,
                                 errors='replace',timeout=3,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if completed.returncode!=0:return None
        hits=[]
        for line in completed.stdout.splitlines()[:limit*4]:
            candidate=Path(line.strip())
            if not candidate.is_absolute() or not _safe_path_in_roots(candidate,allowed_roots):continue
            # Even if ES indexes private paths, never expose those through BARQ.
            if allowed_roots and not any(contained(str(candidate),[str(p)]) for p in allowed_roots):continue
            if extension and candidate.suffix.lower()!=('.'+extension.removeprefix('.').lower()):continue
            hits.append({'name':candidate.name,'path':str(candidate),'extension':candidate.suffix.lower(),'source':'Everything'})
            if len(hits)>=limit:break
        return hits
    except (OSError,subprocess.TimeoutExpired):return None


def search(query:str,*,extension:str='',limit:int=15,allowed_folders:list[str]|None=None)->dict:
    cfg=settings()
    if not cfg['enabled']:return {'status':'permission_required','results':[], 'message':'فهرسة الملفات غير مفعّلة؛ فعّلها في إعدادات الكمبيوتر.'}
    if not isinstance(query,str) or not 2<=len(query.strip())<=150 or any(x in query for x in '\r\n\0'):
        return {'status':'invalid_query','results':[]}
    if not isinstance(extension,str) or not re.fullmatch(r'\.?[a-zA-Z0-9]{0,12}',extension):return {'status':'invalid_extension','results':[]}
    limit=min(max(int(limit),1),_MAX_REPLY)
    roots=scan_roots(cfg,allowed_folders or [])
    if not roots:return {'status':'no_roots','results':[]}
    found=_everything_search(query.strip(),extension,limit,roots)
    # A valid Everything/es.exe CLI can still return NO matches for an
    # explicitly consented folder that it has not indexed (e.g. a new USB
    # disk or user's just-created test folder). An empty accelerated result
    # is not proof of absence: check BARQ's own approved SQLite index too.
    # Neither path reads file contents or bypasses the root safety filters.
    if found:
        return {'status':'ok','engine':'Everything','results':found,'index':status()}
    try:
        with closing(_connect()) as db:
            # Literal LIKE; never interpolate input into SQL.
            needle=query.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            params=['%'+needle+'%']
            where="name LIKE ? ESCAPE '\\'"
            if '/' in query or '\\' in query:
                where="(name LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\')";params=params*2
            if extension:
                where+=' AND extension=?';params+=['.'+extension.removeprefix('.').lower()]
            rows=db.execute('SELECT path,name,extension,size,modified FROM files WHERE '+where+' ORDER BY modified DESC LIMIT ?',(*params,limit*3)).fetchall()
        hits=[{'path':path,'name':name,'extension':ext,'size':size,'modified':mod,'source':'local-index'}
              for path,name,ext,size,mod in rows if _safe_path_in_roots(Path(path),roots) and any(contained(path,[str(r)]) for r in roots)][:limit]
        current=status()
        # An empty initial index is not evidence that a file is absent. Kick
        # off the consented background crawl once, rather than silently
        # reporting no matches forever on a fresh installation.
        if not hits and current['status'] in ('idle', 'failed'):
            with closing(_connect()) as probe:
                has_inventory=probe.execute('SELECT 1 FROM files LIMIT 1').fetchone() is not None
            if not has_inventory:
                started=refresh(allowed_folders or [])
                current=status()
                if started.get('status') in ('indexing', 'ready'):
                    return {'status':'indexing', 'engine':'local-index', 'results':[],
                            'index':current, 'message':'جاري فهرسة الملفات المسموح بها؛ أعد البحث بعد اكتمال الفهرسة.'}
        return {'status':'ok' if hits else current['status'], 'engine':'local-index','results':hits,'index':current}
    except (sqlite3.DatabaseError, OSError):
        return {'status':'index_unavailable','results':[]}

_VIDEO_EXTS=('.mkv','.mp4','.avi','.mov','.wmv','.m4v','.webm','.mpg','.mpeg')

def browse_movies(*,query:str='',allowed_folders:list[str]|None=None,limit:int=18,include_paths:bool=False)->dict:
    """Read-only global video inventory of an explicitly enabled index."""
    cfg=settings()
    if not cfg['enabled']:
        return {'status':'permission_required','movies':[],'message':'فهرسة ملفات الكمبيوتر مقفولة.'}
    roots=scan_roots(cfg,allowed_folders or [])
    if not roots:return {'status':'no_roots','movies':[]}
    if not isinstance(query,str) or len(query)>120:return {'status':'invalid_query','movies':[]}
    from services.local_media import _quality,_display_title
    try:
        # Query many recent candidates, then prefer copies marked as high resolution.
        with closing(_connect()) as db:
            where='extension IN ('+','.join('?' for _ in _VIDEO_EXTS)+')'
            params:list= [*_VIDEO_EXTS]
            if query.strip():
                where+=' AND name LIKE ?';params.append('%'+query.strip().replace('%','\\%').replace('_','\\_')+'%')
            rows=db.execute('SELECT path,name,size,modified FROM files WHERE '+where+
                            ' ORDER BY size DESC LIMIT 400',params).fetchall()
        ranked=[]
        for path,name,size,_ in rows:
            if not _safe_path_in_roots(Path(path),roots) or not any(contained(path,[str(root)]) for root in roots):continue
            if size<2*1024*1024:continue
            quality,rank=_quality(name)
            ranked.append({'name':_display_title(name),'filename':name[:150],
                           'quality':quality,'size_gb':round(size/1e9,2),
                           'folder':Path(path).parent.name[:70], '_path':str(Path(path).resolve()), '_rank':rank,'_size':size})
        ranked.sort(key=lambda x:(x['_rank'],x['_size']),reverse=True)
        return {'status':'ok' if ranked else status()['status'],
                'movies':[{k:v for k,v in m.items() if not k.startswith('_') or (include_paths and k=='_path')} for m in ranked[:min(limit,30)]],
                'count_found':len(ranked),'searched_folders':['فهرس الملفات المحلي'],
                'truncated':len(rows)>=400,'engine':'local-index',
                'note':'نتائج من فهرس الملفات على الأقراص المسموحة؛ جودة النسخة مش تقييم الفيلم، ولم يتم تشغيل أو رفع الملفات.'}
    except sqlite3.DatabaseError:
        return {'status':'index_unavailable','movies':[]}

_install_lock=threading.Lock()
_install_worker:threading.Thread|None=None
_install_state={'status':'idle','step':'','message':''}


def _install_search_components(winget:str):
    # Fixed, verified publisher package IDs; no model-supplied packages or shell.
    packages=('voidtools.Everything','voidtools.Everything.Cli')
    for package in packages:
        with _install_lock:_install_state.update(step=package,status='running')
        try:
            completed=subprocess.run([winget,'install','--id',package,'--exact',
                    '--accept-package-agreements','--accept-source-agreements'],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired) as exc:
            with _install_lock:_install_state.update(status='failed',message=type(exc).__name__)
            return
        if completed.returncode not in (0,):
            with _install_lock:_install_state.update(status='failed',message=f'winget exit {completed.returncode}, component {package}')
            return
    with _install_lock:_install_state.update(status='finished',message='Everything و ES CLI اتثبتوا. ممكن تحتاج تعيد تشغيل برق لتحديث PATH.')


def install_status()->dict:
    with _install_lock:return dict(_install_state)


def request_official_search_install(*,approved:bool)->dict:
    """Install official Everything + CLI only after an on-screen user click.

    Cannot be invoked by a model function. Windows can request UAC separately.
    """
    global _install_worker
    if sys.platform!='win32':return {'status':'unsupported'}
    if approved is not True:return {'status':'approval_required'}
    winget=shutil.which('winget.exe') or shutil.which('winget')
    if not winget:return {'status':'winget_missing','message':'Windows App Installer (winget) غير متاح.'}
    with _install_lock:
        if _install_worker and _install_worker.is_alive():return {'status':'running'}
        _install_state.update(status='running',message='',step='preparing')
        _install_worker=threading.Thread(target=_install_search_components,args=(winget,),daemon=True,name='barq-search-installer')
        _install_worker.start()
    return {'status':'started','message':'بدأ تثبيت Everything وأداة ES CLI الرسمية بعد موافقتك. راقب حالة التثبيت في الإعدادات، وأعد تشغيل برق لو لزم تحديث PATH.'}
