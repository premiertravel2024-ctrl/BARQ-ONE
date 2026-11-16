"""Persistent per-conversation missions and redacted evidence, separate from model memory."""
from core.sqlite import connect as barq_sqlite_connect
import json
from pathlib import Path
import sqlite3
import time
import uuid
from coding.redaction import redact
from core.paths import state_file

TERMINAL={'completed','cancelled','superseded'}


class TaskStore:
    def __init__(self,path=None):
        self.path=str(path or state_file('brain.sqlite3'))
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS brain_tasks (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS brain_conversation ON brain_tasks(conversation_id,updated)')

    def connect(self):
        return barq_sqlite_connect(self.path,timeout=10)

    def _put(self,task):
        task={**task,'updated':time.time(),'revision':task.get('revision',0)+1}
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO brain_tasks VALUES (?,?,?,?)',
                       (task['id'],task['conversation_id'],json.dumps(task,ensure_ascii=False),task['updated']))
        return task

    def get(self,task_id):
        with self.connect() as db:row=db.execute('SELECT data FROM brain_tasks WHERE id=?',(task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def latest(self,conversation_id):
        if not conversation_id:return None
        with self.connect() as db:
            row=db.execute('SELECT data FROM brain_tasks WHERE conversation_id=? ORDER BY updated DESC LIMIT 1',(conversation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def for_pending(self,field,token):
        if field not in ('plan_id','approval_id','retry_id') or not token:return None
        with self.connect() as db:
            rows=db.execute('SELECT data FROM brain_tasks ORDER BY updated DESC LIMIT 200').fetchall()
        return next((item for row in rows if (item:=json.loads(row[0])).get(field)==token),None)

    def begin(self,conversation_id,kind,goal,workspace,runtime_id):
        old=self.latest(conversation_id)
        if old and old['status'] not in TERMINAL:
            self.update(old['id'],status='superseded')
        return self._put({'id':uuid.uuid4().hex,'conversation_id':conversation_id,'kind':kind,
            'goal':redact(goal)[:12000],'workspace':workspace,'status':'planning','runtime_id':runtime_id,
            'plan_id':None,'approval_id':None,'evidence':[],'events':[],'model':None,'saved_paths':[]})

    def update(self,task_id,**patch):
        return self._mutate(task_id, lambda task: {**task, **patch})

    def _mutate(self, task_id, change):
        # Read-modify-write must share one write transaction. Separate get/put
        # transactions silently lost events when API requests overlapped.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM brain_tasks WHERE id=?',(task_id,)).fetchone()
            if not row:raise ValueError('Task not found')
            old=json.loads(row[0])
            task={**change(old),'updated':time.time(),'revision':old.get('revision',0)+1}
            db.execute('UPDATE brain_tasks SET data=?, updated=? WHERE id=?',
                       (json.dumps(task,ensure_ascii=False),task['updated'],task_id))
            return task

    def event(self,task_id,kind,label,success=None):
        event={'at':time.time(),'kind':kind,'label':redact(str(label))[:250],'success':success}
        return self._mutate(task_id,lambda task:{**task,'events':(task.get('events',[])+[event])[-40:]})

    def evidence(self,task_id,entries):
        evidence=[]
        for entry in entries:
            item={key:entry[key] for key in ('tool','success','result','error','truncated','verification') if key in entry}
            for key in ('result','error'):
                if key in item:item[key]=redact(str(item[key]))[:4000]
            evidence.append(item)
        def append(task):
            completed=list(dict.fromkeys(task.get('completed_tools',[])+[
                entry.get('tool') for entry in entries if entry.get('success')]))
            checks=list(task.get('checks_after_save',[]))
            for entry in entries:
                tool=entry.get('tool')
                if tool in {'run_tests','code_check','project_build'}:
                    if tool in checks:checks.remove(tool)
                    if entry.get('success'):checks.append(tool)
            return {**task,'evidence':(task.get('evidence',[])+evidence)[-40:],
                    'completed_tools':completed,'checks_after_save':checks}
        return self._mutate(task_id,append)

    def public(self,task):
        if not task:return None
        # Tool contents, source, credentials and opaque approval tokens are not
        # exposed by the passive progress monitor.
        return {k:task.get(k) for k in ('id','conversation_id','kind','goal','status','revision','updated','events','saved_paths')}
