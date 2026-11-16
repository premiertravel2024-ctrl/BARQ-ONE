"""Bounded local metadata-only indexes. Never read file contents or enumerate secrets."""
from __future__ import annotations
from core.sqlite import connect as barq_sqlite_connect
import json,os,sqlite3,subprocess,sys,time,shutil,threading
from collections import deque
from pathlib import Path
from core.paths import state_file
from computer_control.safety.policy import sensitive
from .nlu import clean

SKIP={'.git','.barq','node_modules','.venv','venv','appdata','windows','system32','program files','program files (x86)','__pycache__'}
# Windows KNOWNFOLDERIDs: desktop, documents, downloads, pictures, music, videos.
KNOWN_GUIDS={
 'desktop':'{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}',
 'documents':'{FDD39AD0-238F-46AF-ADB4-6C85480369C7}',
 'downloads':'{374DE290-123F-4565-9164-39C4925E467B}',
 'pictures':'{33E28130-4E1E-4676-835A-98395C3BC3BB}',
 'videos':'{18989B1D-99B5-455B-841C-AB7C74E4DDFC}',
 'music':'{4BD8D571-6D19-48D3-BE97-422220080E43}',
}

def known_folder(name):
    if name not in KNOWN_GUIDS:raise ValueError('Unknown known folder')
    if sys.platform!='win32':return Path.home()/name.title()
    import ctypes,uuid
    from ctypes import wintypes
    guid=uuid.UUID(KNOWN_GUIDS[name]); raw=(ctypes.c_ubyte*16).from_buffer_copy(guid.bytes_le)
    ptr=ctypes.c_wchar_p()
    get=ctypes.windll.shell32.SHGetKnownFolderPath
    get.argtypes=[ctypes.c_void_p,wintypes.DWORD,wintypes.HANDLE,ctypes.POINTER(ctypes.c_wchar_p)]
    get.restype=ctypes.c_long
    rc=get(ctypes.byref(raw),0,None,ctypes.byref(ptr))
    if rc!=0:raise OSError('Unable to resolve Windows known folder')
    try:return Path(ptr.value)
    finally:ctypes.windll.ole32.CoTaskMemFree(ptr)

def exact_name(label,query,kind):
    return clean(label)==clean(query) or (kind=='file' and not Path(query).suffix and clean(Path(label).stem)==clean(query))

class Index:
    def __init__(self,path:Path|None=None,roots:list[Path]|None=None,max_entries:int=20000,max_depth:int=5):
        self._folder_lock=threading.Lock()
        self.last_folder_search={}
        self.path=path or state_file('launcher_index.sqlite')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.roots=roots
        self.max_entries=min(max_entries,50000)
        self.max_depth=min(max_depth,8)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY,kind TEXT NOT NULL,label TEXT NOT NULL,path TEXT NOT NULL,mtime REAL NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS lookup_label ON entries(label)')
            db.execute('CREATE INDEX IF NOT EXISTS lookup_label_nocase ON entries(label COLLATE NOCASE)')
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT)')
    def connect(self):return barq_sqlite_connect(str(self.path),timeout=5)
    def default_roots(self):
        roots=[]
        for name in KNOWN_GUIDS:
            try:
                path=known_folder(name)
                if path.is_dir() and not sensitive(str(path)):roots.append(path)
            except (OSError,ValueError):continue
        return roots
    def allowed_roots(self):
        result=[]
        for folder in (self.roots if self.roots is not None else self.default_roots()):
            try:
                p=Path(folder).expanduser().resolve(strict=True)
                if p.is_dir() and not sensitive(str(p)) and p not in result:result.append(p)
            except (OSError,ValueError):pass
        return result
    def reindex(self):
        rows=[];count=0;roots=self.allowed_roots()
        for root in roots:
            stack=[(root,0)]
            while stack and count<self.max_entries:
                folder,depth=stack.pop()
                if sensitive(str(folder)) or depth>self.max_depth:continue
                ignored=set()
                ignore=folder/'.barqignore'
                if ignore.is_file():
                    try:ignored={line.strip() for line in ignore.read_text(encoding='utf-8').splitlines()[:200] if line.strip() and not line.startswith('#')}
                    except OSError:pass
                try:
                    with os.scandir(folder) as scan:
                        for ent in scan:
                            if count>=self.max_entries:break
                            if ent.name.lower() in SKIP or ent.name in ignored or ent.is_symlink():continue
                            if ent.name.startswith('.') and ent.name.lower()!='.pdf':continue
                            path=Path(ent.path)
                            if sensitive(str(path)):continue
                            try:
                                is_dir=ent.is_dir(follow_symlinks=False)
                                info=ent.stat(follow_symlinks=False)
                            except (OSError,ValueError):continue
                            if is_dir and depth<self.max_depth:stack.append((path,depth+1))
                            if not (is_dir or ent.is_file(follow_symlinks=False)):continue
                            value=str(path)
                            rows.append((value,'folder' if is_dir else 'file',path.name,value,info.st_mtime))
                            count+=1
                except (OSError,PermissionError):continue
        with self.connect() as db:
            db.execute('DELETE FROM entries')
            db.executemany('INSERT INTO entries VALUES(?,?,?,?,?)',rows)
            db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('refreshed',str(time.time())))
        return {'entries':count,'refreshed':time.time()}
    def find_paths(self,term:str,*,kind:str="folder",extra_roots=(),max_seconds:float=1.5,max_entries:int=6000):
        """Exact local folder lookup, then a bounded breadth-first metadata scan.

        A cold/empty index never sends a simple folder command to a model.
        Partial names are suggestions only; Resolver must not auto-open them.
        """
        target=clean(term);started=time.monotonic()
        if not target or len(target)>240:return []
        with self.connect() as db:
            cached=db.execute("SELECT kind,label,path,mtime FROM entries WHERE kind=? AND label=? COLLATE NOCASE LIMIT 30",(kind,term.strip())).fetchall()
        exact=[];seen=set()
        for typ,label,path,mtime in cached:
            try:
                actual=Path(path)
                if actual.is_symlink() or getattr(actual.stat(follow_symlinks=False),'st_file_attributes',0)&0x400:continue
                if (actual.is_dir() if kind=='folder' else actual.is_file()) and not sensitive(path) and exact_name(actual.name,term,kind):
                    resolved=str(actual.resolve(strict=True))
                    if resolved not in seen:
                        exact.append({'kind':kind,'label':actual.name,'path':resolved,'mtime':mtime,'score':1.0});seen.add(resolved)
            except (OSError,ValueError):continue
        indexed_partial=[]
        if self.roots is None:
            from services.name_search import indexed_names
            for hit in indexed_names(term,kind,[*self.allowed_roots(),*extra_roots]):
                if hit['path'] not in seen:
                    (exact if hit['score']==1 else indexed_partial).append(hit)
                    if hit['score']==1:seen.add(hit['path'])
        if exact:
            self.last_folder_search={'engine':'cache','truncated':False,'elapsed':time.monotonic()-started}
            return (exact+indexed_partial)[:25] if kind=='file' and not any(clean(item['label'])==target for item in exact) else exact
        if not self._folder_lock.acquire(blocking=False):
            self.last_folder_search={'engine':'local-scan','truncated':True,'busy':True,'elapsed':0}
            return []
        try:
            roots=self.allowed_roots()
            for folder in extra_roots:
                try:
                    root=Path(folder).expanduser().resolve(strict=True)
                    if root.is_dir() and not sensitive(str(root)) and root not in roots:roots.append(root)
                except (OSError,ValueError):continue
            queue=deque((root,0) for root in roots);visited=set();partial=indexed_partial;count=0
            deadline=started+max_seconds;truncated=False
            while queue:
                if time.monotonic()>=deadline or count>=max_entries:truncated=True;break
                folder,depth=queue.popleft()
                try:
                    stat=folder.stat(follow_symlinks=False)
                    if folder.is_symlink() or getattr(stat,'st_file_attributes',0)&0x400:continue
                    ident=(stat.st_dev,stat.st_ino)
                    if ident in visited:continue
                    visited.add(ident)
                    name=clean(folder.name)
                    if kind=='folder' and str(folder) not in seen and (name==target or target in name):
                        item={'kind':'folder','label':folder.name,'path':str(folder.resolve(strict=True)),'mtime':stat.st_mtime,'score':1.0 if name==target else .8}
                        (exact if name==target else partial).append(item);seen.add(str(folder))
                    if depth>=self.max_depth:continue
                    with os.scandir(folder) as scan:
                        for entry in scan:
                            if time.monotonic()>=deadline or count>=max_entries:truncated=True;break
                            count+=1
                            if entry.name.casefold() in SKIP or entry.name.startswith('.') or entry.is_symlink():continue
                            if sensitive(entry.path):continue
                            if entry.is_dir(follow_symlinks=False):
                                child=Path(entry.path);queue.append((child,depth+1))
                                name=clean(entry.name)
                                if kind=='folder' and (name==target or target in name):
                                    stat=entry.stat(follow_symlinks=False)
                                    if getattr(stat,'st_file_attributes',0)&0x400:continue
                                    path=str(child.resolve(strict=True))
                                    if path not in seen:
                                        item={'kind':'folder','label':entry.name,'path':path,'mtime':stat.st_mtime,'score':1.0 if name==target else .8}
                                        (exact if name==target else partial).append(item);seen.add(path)
                            elif kind=='file' and entry.is_file(follow_symlinks=False):
                                name=clean(entry.name)
                                if name==target or target in name:
                                    stat=entry.stat(follow_symlinks=False);path=str(Path(entry.path).resolve(strict=True))
                                    if path not in seen:
                                        item={'kind':'file','label':entry.name,'path':path,'mtime':stat.st_mtime,'score':1.0 if exact_name(entry.name,term,'file') else .8}
                                        (exact if exact_name(entry.name,term,'file') else partial).append(item);seen.add(path)
                except (OSError,ValueError):continue
            hits=((exact+partial) if kind=='file' and exact and not any(clean(item['label'])==target for item in exact) else (exact or partial))[:25]
            if hits:
                with self.connect() as db:
                    db.executemany('INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?)',[(hit['path'],kind,hit['label'],hit['path'],hit['mtime']) for hit in hits])
            self.last_folder_search={'engine':'local-scan','truncated':truncated,'entries':count,'elapsed':time.monotonic()-started}
            return hits
        finally:self._folder_lock.release()

    def find_folders(self,term:str,**options):
        return self.find_paths(term,kind='folder',**options)

    def search(self,term:str,kind:str|None=None,exts:tuple[str,...]=(),limit:int=25):
        q=clean(term)
        output=[]
        with self.connect() as db:
            # Bound index size; metadata-only filenames. No contents are read.
            cursor=db.execute('SELECT kind,label,path,mtime FROM entries'+(' WHERE kind=?' if kind in ('file','folder') else ''), (kind,) if kind in ('file','folder') else ())
            for typ,label,path,mtime in cursor:
                n=clean(label)
                if exts and typ=='file' and not label.lower().endswith(exts):continue
                if q==n:score=1.
                elif q in n:score=.91
                else:
                    from difflib import SequenceMatcher
                    score=SequenceMatcher(None,q,n).ratio()
                if score<.66:continue
                output.append({'kind':typ,'label':label,'path':path,'score':score,'mtime':mtime})
        output.sort(key=lambda x:(-x['score'],-x['mtime']))
        return output[:limit]
    def apps(self):
        output=[];seen=set()
        if sys.platform!='win32':return output
        for env,suffix in [('APPDATA','Microsoft/Windows/Start Menu/Programs'),('PROGRAMDATA','Microsoft/Windows/Start Menu/Programs')]:
            base=os.getenv(env)
            if not base:continue
            root=Path(base)/suffix
            if not root.is_dir():continue
            for p in root.rglob('*.lnk'):
                if len(output)>=3000:break
                # Start Menu is an explicit OS metadata root; user AppData alone must not hide shortcuts.
                # It does not grant permission to read any other AppData contents.
                if str(p).lower() in seen:continue
                seen.add(str(p).lower());output.append({'label':p.stem,'path':str(p),'kind':'app','appid':None})
        # Fixed PowerShell program/arguments only; no user-controlled shell text.
        try:
            run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
                'Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress'],capture_output=True,text=True,timeout=8,check=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if run.returncode==0 and run.stdout.strip():
                data=json.loads(run.stdout)
                for ent in data if isinstance(data,list) else [data]:
                    name=ent.get('Name');appid=ent.get('AppID')
                    if name and appid:output.append({'label':str(name)[:100],'path':None,'kind':'app','appid':str(appid)[:250]})
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        # Read-only Windows App Paths registry entries. No program is run here.
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
                try:reg=winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths')
                except OSError:continue
                with reg:
                    n=winreg.QueryInfoKey(reg)[0]
                    for i in range(min(n,2500)):
                        try:
                            subname=winreg.EnumKey(reg,i)
                            with winreg.OpenKey(reg,subname) as sub:
                                location=winreg.QueryValueEx(sub,None)[0]
                            if isinstance(location,str) and Path(location).is_file() and not sensitive(location):
                                output.append({'label':Path(subname).stem,'path':location,'kind':'app','appid':None})
                        except (OSError,ValueError):continue
        except ImportError:pass
        # Only recognizable names are included; do not scan the entire PATH filesystem.
        for name in ('notepad','calc','code','chrome','firefox','msedge','winword','excel','powerpnt'):
            found=shutil.which(name)
            if found and not sensitive(found):output.append({'label':name,'path':found,'kind':'app','appid':None})
        return output
    def status(self):
        with self.connect() as db:
            count=db.execute('SELECT kind, COUNT(*) FROM entries GROUP BY kind').fetchall()
            last=db.execute("SELECT value FROM meta WHERE key='refreshed'").fetchone()
        return {'counts':dict(count),'refreshed':float(last[0]) if last else None,'roots':[str(x) for x in self.allowed_roots()]}
