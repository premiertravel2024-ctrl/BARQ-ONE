"""Persist explicit per-project grants. Never infer consent from model text."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
import json,os,threading,time,uuid
from computer_control.safety.policy import sensitive, resolve_path
from core.paths import state_file

SCOPES=frozenset({'read','write','create','run_tests','build','install_dependencies','run_dev_server','git_local'})

@dataclass(frozen=True)
class ProjectGrant:
    id:str
    root:str
    label:str
    scopes:tuple[str,...]
    created_at:float
    expires_at:float|None=None

    def allows(self,path:str,scope:str)->bool:
        if scope not in self.scopes or self.expires_at is not None and time.time()>self.expires_at:
            return False
        resolved=resolve_path(path)
        try:resolved.relative_to(resolve_path(self.root))
        except ValueError:return False
        return not sensitive(str(resolved))

class GrantStore:
    def __init__(self,path:Path|None=None):
        self.path=Path(path or state_file('execution_project_grants.json'))
        self._lock=threading.RLock()

    @staticmethod
    def validate_root(root:str)->Path:
        folder=resolve_path(root)
        if not folder.is_dir() or sensitive(str(folder)):
            raise ValueError('Project folder missing or protected')
        anchor=Path(folder.anchor)
        if folder==anchor or folder==Path.home().resolve() or folder==Path(os.environ.get('USERPROFILE',str(Path.home()))).resolve():
            raise ValueError('Cannot grant an entire drive or the user profile')
        if os.name=='nt' and folder.parent==anchor:
            raise ValueError('Select a specific project subfolder, not a drive-level directory')
        return folder

    def all(self)->list[ProjectGrant]:
        with self._lock:
            try:raw=json.loads(self.path.read_text(encoding='utf-8'))
            except FileNotFoundError:return []
            if not isinstance(raw,list):raise ValueError('Invalid project grants store')
            return [ProjectGrant(**{**item,'scopes':tuple(item['scopes'])}) for item in raw]

    def _write(self,grants:Iterable[ProjectGrant]):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(self.path.suffix+'.tmp')
        temp.write_text(json.dumps([asdict(g) for g in grants],ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(self.path)

    def grant(self,root:str,scopes:Iterable[str],label:str='',expires_at:float|None=None)->ProjectGrant:
        path=self.validate_root(root)
        selected=tuple(sorted(set(scopes)))
        if not selected or not set(selected)<=SCOPES:raise ValueError('Unknown grant scope')
        if expires_at is not None and expires_at<=time.time():raise ValueError('Grant already expired')
        value=ProjectGrant(uuid.uuid4().hex,str(path),label[:100] or path.name,selected,time.time(),expires_at)
        with self._lock:self._write([g for g in self.all() if g.root!=str(path)]+[value])
        return value

    def revoke(self,grant_id:str)->bool:
        with self._lock:
            previous=self.all();new=[g for g in previous if g.id!=grant_id]
            self._write(new)
            return len(previous)!=len(new)

    def revoke_all(self):
        with self._lock:self._write([])

    def permits(self,path:str,scope:str)->bool:
        return any(g.allows(path,scope) for g in self.all())
