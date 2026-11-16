"""Workspace-limited explorer, guarded writes with backups and readable diffs."""
from pathlib import Path
import difflib, os, uuid, time, json, re, hashlib
from core.paths import state_file

MAX_READ=512*1024
MAX_WRITE=512*1024
PENDING={}
EXTENSIONS={'.py','.js','.jsx','.ts','.tsx','.json','.yaml','.yml','.toml','.md','.txt','.html','.css','.scss','.rs','.go','.java','.sql','.xml','.ini','.cfg','.ps1','.bat','.sh','.gitignore','.env.example'}
BLOCKED={'.barq-venv','.env','.git','node_modules','.venv','dist','build','.next','__pycache__'}

def root_of(workspace):
    root=Path(workspace).expanduser().resolve(strict=True)
    if not root.is_dir():raise ValueError('Workspace is not a directory')
    return root

def checked_path(workspace, relative, write=False, *, allow_missing_parent=False):
    root=root_of(workspace)
    rel=Path(relative)
    if rel.is_absolute() or not rel.parts or '..' in rel.parts or any(x in BLOCKED for x in rel.parts) or any(
        (x.startswith('.env') and x != '.env.example') or re.search(r'(?i)(secret|private.?key|credential|token|id_rsa)', x)
        for x in rel.parts):
        raise ValueError('Invalid workspace-relative path')
    path=(root/rel).resolve()
    if not path.is_relative_to(root):raise ValueError('Path escapes workspace')
    if write and path.suffix.lower() not in EXTENSIONS:raise ValueError('File type not allowed for editor')
    if not allow_missing_parent and not path.parent.is_dir():raise ValueError('Parent directory does not exist')
    return path

def listing(workspace, relative=''):
    root=root_of(workspace)
    target=root if not relative else checked_path(workspace,relative)
    if not target.is_dir():raise ValueError('Not a directory')
    out=[]
    for node in sorted(target.iterdir(),key=lambda p:(p.is_file(),p.name.lower())):
        if node.name in BLOCKED or node.name.startswith('.env') or node.is_symlink():continue
        if len(out)>=200:break
        if not node.resolve().is_relative_to(root):continue
        out.append({'name':node.name,'path':node.relative_to(root).as_posix(),'is_dir':node.is_dir(),'size':node.stat().st_size if node.is_file() else None})
    return out

def read_text(workspace,path):
    p=checked_path(workspace,path)
    if not p.is_file() or p.stat().st_size>MAX_READ:raise ValueError('File missing or too large')
    if p.suffix.lower() not in EXTENSIONS:raise ValueError('Text file type not allowed')
    try:return p.read_text(encoding='utf-8')
    except UnicodeDecodeError:raise ValueError('File is not UTF-8 text')

class FileConflict(ValueError):
    """The editor/preview no longer describes the version on disk."""

def snapshot(workspace,path):
    p=checked_path(workspace,path,True)
    if not p.exists():return {'path':path,'content':'','revision':'missing','exists':False}
    if not p.is_file() or p.stat().st_size>MAX_READ:raise ValueError('File missing or too large')
    raw=p.read_bytes()
    if len(raw)>MAX_READ:raise ValueError('File too large')
    try:content=raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    except UnicodeDecodeError:raise ValueError('File is not UTF-8 text')
    return {'path':path,'content':content,'revision':hashlib.sha256(raw).hexdigest(),'exists':True}

def propose(workspace,path,new_content,expected_revision=None):
    if len(new_content.encode('utf-8'))>MAX_WRITE:raise ValueError('Edit too large')
    p=checked_path(workspace,path,True)
    current=snapshot(workspace,path)
    if expected_revision is not None and expected_revision!=current['revision']:
        raise FileConflict('الملف اتغير على القرص منذ فتحه. حدّث الملف وراجع الفرق قبل الحفظ.')
    before=current['content']
    diff=''.join(difflib.unified_diff(before.splitlines(True),new_content.splitlines(True),fromfile=path+' (before)',tofile=path+' (proposed)'))
    token=uuid.uuid4().hex
    PENDING[token]={'workspace':str(root_of(workspace)),'path':path,'before':before,'revision':current['revision'],'content':new_content,'expires':time.monotonic()+600}
    return {'approval_id':token,'path':path,'diff':diff[:40000],'changed':before!=new_content,'expires_in_seconds':600}

def apply(approval_id,confirmed=False):
    if not confirmed:raise ValueError('Confirmation required')
    change=PENDING.pop(approval_id,None)
    if not change or time.monotonic()>change['expires']:raise ValueError('Edit approval expired')
    p=checked_path(change['workspace'],change['path'],True)
    disk=snapshot(change['workspace'],change['path']);current=disk['content']
    if disk['revision']!=change['revision']:raise FileConflict('File changed since preview; propose again')
    backups=state_file('edit-backups');backups.mkdir(parents=True,exist_ok=True)
    uid=uuid.uuid4().hex
    (backups/(uid+'.json')).write_text(json.dumps({'workspace':change['workspace'],'path':change['path'],'before':current,'after':change['content'],'was_present':p.exists()},ensure_ascii=False),encoding='utf-8')
    temp=p.with_name(p.name+'.ai-router-'+uid+'.tmp')
    try:
        temp.write_text(change['content'],encoding='utf-8')
        os.replace(temp,p)
    finally:
        if temp.exists():temp.unlink()
    try:
        from services.personal_assistant import remember
        remember('last_backup',uid);remember('last_edit_path',str(p))
    except OSError:pass
    return {'path':change['path'],'workspace':change['workspace'],'backup_id':uid,'saved':True,'revision':hashlib.sha256(p.read_bytes()).hexdigest()}

def undo(backup_id,confirmed=False):
    if not confirmed:raise ValueError('Confirmation required')
    if len(backup_id)!=32 or any(x not in '0123456789abcdef' for x in backup_id):raise ValueError('Invalid ID')
    f=state_file('edit-backups')/(backup_id+'.json')
    if not f.exists():raise ValueError('Backup not found')
    saved=json.loads(f.read_text(encoding='utf-8'))
    p=checked_path(saved['workspace'],saved['path'],True)
    now=read_text(saved['workspace'],saved['path']) if p.exists() else ''
    if now!=saved['after']:raise ValueError('File changed; cannot safely undo')
    if not saved['was_present']:p.unlink(missing_ok=True)
    else:p.write_text(saved['before'],encoding='utf-8')
    f.unlink()
    return {'restored':saved['path'],'workspace':saved['workspace']}
