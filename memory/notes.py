"""Bounded, explicit-only local project notes. Not self-learning or biometric data.

Only the user can add/remove notes, they are never automatically transmitted to
models, and an external page/email cannot create memories. No credentials allowed.
"""
from __future__ import annotations
import os
import sqlite3
import time
import uuid
from pathlib import Path
from core.paths import data_dir
from computer_control.safety.policy import SECRET


class Notes:
    def __init__(self,path:Path|None=None):
        self.path=Path(path or (data_dir()/'barq_explicit_notes.sqlite3'))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if not self.path.exists() and os.name!='nt':
            fd=os.open(self.path,os.O_CREAT|os.O_WRONLY,0o600);os.close(fd)
        with self._db() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL)''')
            con.execute('CREATE INDEX IF NOT EXISTS ix_notes_project ON notes(project)')

    def _db(self):return sqlite3.connect(self.path,timeout=4)

    @staticmethod
    def _validate(project:str,content:str):
        if not isinstance(project,str) or not 1<=len(project.strip())<=80:raise ValueError('Invalid project')
        if not isinstance(content,str) or not 3<=len(content.strip())<=1000:raise ValueError('Invalid note')
        if SECRET.search(content) or any(x in content.lower() for x in ('password=', 'api key=', 'bearer ', 'private key')):
            raise ValueError('Never store secrets in BARQ notes')

    def add(self,project:str,content:str)->dict:
        self._validate(project,content)
        note={'id':uuid.uuid4().hex,'project':project.strip(),'text':content.strip(),'created':int(time.time())}
        with self._db() as db:
            if db.execute('SELECT COUNT(*) FROM notes').fetchone()[0]>=250:
                raise ValueError('Note limit reached: delete old notes')
            db.execute('INSERT INTO notes VALUES(?,?,?,?)',tuple(note[k] for k in ('id','project','text','created')))
        return note

    def search(self,query:str='',project:str='',limit:int=20)->list[dict]:
        if not isinstance(query,str) or len(query)>100:raise ValueError('Invalid search')
        if not isinstance(project,str) or len(project)>80:raise ValueError('Invalid project')
        limit=min(40,max(1,limit))
        clauses=[];params=[]
        if query.strip():clauses.append('text LIKE ? ESCAPE \'\\\'');params.append('%'+query.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        if project.strip():clauses.append('project = ?');params.append(project.strip())
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self._db() as db:
            rows=db.execute('SELECT id,project,text,created FROM notes'+where+' ORDER BY created DESC LIMIT ?',(*params,limit)).fetchall()
        return [dict(zip(('id','project','text','created'),r)) for r in rows]

    def delete(self,note_id:str)->bool:
        if not isinstance(note_id,str) or len(note_id)!=32 or not note_id.isalnum():
            raise ValueError('Invalid note ID')
        with self._db() as db:result=db.execute('DELETE FROM notes WHERE id=?',(note_id,))
        return result.rowcount==1


_store:Notes|None=None
def notes()->Notes:
    global _store
    if _store is None:_store=Notes()
    return _store
