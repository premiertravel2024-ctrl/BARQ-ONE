"""Local, user-controlled project notes and a metadata-only agent activity log.

Project notes are never inserted into cloud requests automatically. The browser
can include them in one request only after the user opts in.
"""
from core.sqlite import connect as barq_sqlite_connect
import hashlib
import sqlite3
import time
from core.paths import state_file
from workspace.manager import root_of

MAX_NOTE=6000


def _key(workspace):
    return hashlib.sha256(str(root_of(workspace)).encode('utf-8')).hexdigest()


def _db():
    location=state_file('project_state.sqlite3')
    connection=barq_sqlite_connect(str(location),timeout=8)
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS project_notes (project text PRIMARY KEY, note text NOT NULL, updated REAL NOT NULL)')
        connection.execute('CREATE TABLE IF NOT EXISTS agent_activity (project text NOT NULL, tool text NOT NULL, success INTEGER NOT NULL, updated REAL NOT NULL)')
    except BaseException:
        connection.close();raise
    return connection


def note(workspace):
    key=_key(workspace)
    with _db() as conn:
        row=conn.execute('SELECT note,updated FROM project_notes WHERE project=?',(key,)).fetchone()
    return {'note':row[0] if row else '', 'updated':row[1] if row else None}


def save_note(workspace,text):
    if not isinstance(text,str) or len(text)>MAX_NOTE:
        raise ValueError('Project note exceeds maximum size')
    key=_key(workspace)
    with _db() as conn:
        conn.execute('INSERT OR REPLACE INTO project_notes VALUES (?,?,?)',(key,text,time.time()))
    return {'saved':True,'characters':len(text)}


def record(workspace,tool,success):
    if not isinstance(tool,str) or not (1<=len(tool)<=60) or not all(c.isalnum() or c in '_-' for c in tool):
        raise ValueError('Invalid activity action')
    key=_key(workspace)
    with _db() as conn:
        # SQLite timestamps can collide on fast machines. Row IDs track write order reliably.
        conn.execute('INSERT INTO agent_activity VALUES (?,?,?,?)',(key,tool,int(bool(success)),time.time()))
        conn.execute('DELETE FROM agent_activity WHERE rowid IN (SELECT rowid FROM agent_activity WHERE project=? ORDER BY rowid DESC LIMIT -1 OFFSET 200)',(key,))


def recent(workspace,limit=50):
    key=_key(workspace)
    with _db() as conn:
        rows=conn.execute('SELECT tool,success,updated FROM agent_activity WHERE project=? ORDER BY rowid DESC LIMIT ?',
                          (key,min(100,max(1,int(limit))))).fetchall()
    return {'actions':[{'tool':tool,'success':bool(success),'at':updated} for tool,success,updated in rows]}
