"""Crash-safe, bounded local checkpoints for desktop tasks.

A saved checkpoint is never permission to act. Restored tasks default to
`interrupted` and require explicit user interaction to continue. Passwords,
UI text, screenshots, tool arguments and model output are not persisted.
"""
from __future__ import annotations

import errno
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.paths import data_dir
from computer_control.safety.policy import redact

ACTIVE = frozenset({'planning', 'running', 'approval'})
ALLOWED = frozenset({'planning', 'running', 'approval', 'stopped', 'failed', 'completed',
                     'needs_review', 'limit', 'interrupted'})


class TaskStateStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or data_dir() / 'computer_control_checkpoints.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                status TEXT NOT NULL, updated REAL NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS ix_tasks_updated ON tasks(updated DESC)')
            db.execute("""CREATE TABLE IF NOT EXISTS steps (
                task_id TEXT NOT NULL, step_id TEXT NOT NULL, tool TEXT NOT NULL,
                args_digest TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL, verification TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL,
                PRIMARY KEY(task_id,step_id))""")

    def _connect(self):
        # Check this for every connection, not just in __init__. A changed,
        # removed, or inaccessible data directory must fail closed before any
        # desktop action starts. SQLite otherwise raises OperationalError on
        # Windows but Linux's secure-create branch raises OSError, which made
        # the same checkpoint failure behave differently across platforms.
        parent = self.path.parent
        if not parent.is_dir():
            if parent.exists():
                raise NotADirectoryError(errno.ENOTDIR, 'BARQ checkpoint parent is not a directory', str(parent))
            raise FileNotFoundError(errno.ENOENT, 'BARQ checkpoint parent directory is missing', str(parent))
        if not self.path.exists() and os.name != 'nt':
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        db = sqlite3.connect(self.path, timeout=4)
        db.execute('PRAGMA busy_timeout=4000')
        return db

    @staticmethod
    def _safe(snapshot: dict[str, Any]) -> dict[str, Any]:
        # Only an explicitly whitelisted, size-limited subset. No screenshots,
        # full tool results, pending approval or credential-bearing arguments.
        history = [{
            'tool': redact(str(h.get('tool', '')))[:64],
            'status': str(h.get('status', ''))[:32],
            'verification': str(h.get('verification', ''))[:32],
            'verification_reason': redact(str(h.get('verification_reason', '')))[:240],
        } for h in snapshot.get('history', [])[-40:] if isinstance(h, dict)]
        return {
            'id': str(snapshot['id'])[:80],
            'goal': redact(str(snapshot.get('goal', '')))[:3000],
            'model': str(snapshot.get('model', 'auto'))[:120],
            'status': str(snapshot.get('status', 'interrupted')) if snapshot.get('status') in ALLOWED else 'interrupted',
            'phase': str(snapshot.get('phase', 'understand'))[:32],
            'source': str(snapshot.get('source', 'text'))[:16],
            'steps': [redact(str(s))[:180] for s in snapshot.get('steps', [])[:40]],
            'history': history,
            'is_sequence': snapshot.get('is_sequence') is True,
            'step_index': snapshot.get('step_index'),
            'verified_steps': min(40,max(0,int(snapshot.get('verified_steps',0)))),
            'progress': min(600, max(0, int(snapshot.get('progress', 0)))),
            'goal_proof': {k: redact(str(v))[:300] for k, v in
                           snapshot.get('goal_proof', {}).items() if k in {'status', 'reason', 'proof'}},
            'message': redact(str(snapshot.get('message', '')))[:300],
        }

    def save(self, snapshot: dict[str, Any]) -> None:
        value = self._safe(snapshot)
        with self._lock, self._connect() as db:
            db.execute('INSERT INTO tasks(id,payload,status,updated) VALUES (?,?,?,?) '
                       'ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, '
                       'status=excluded.status, updated=excluded.updated',
                       (value['id'], json.dumps(value, ensure_ascii=False), value['status'], time.time()))
            # Bounded history, sorted by update age.
            db.execute('DELETE FROM tasks WHERE id NOT IN '
                       '(SELECT id FROM tasks ORDER BY updated DESC LIMIT 60)')

    def step_started(self,task_id:str,step_id:str,tool:str,args_digest:str,idempotency_key:str)->None:
        """Persist start BEFORE executing; only a digest, never raw arguments."""
        import re
        if not re.fullmatch(r'[a-f0-9]{64}',args_digest):raise ValueError('Argument digest must be SHA-256')
        if not all(isinstance(x,str) and 0<len(x)<=100 for x in (task_id,step_id,tool,idempotency_key)):
            raise ValueError('Invalid step identity')
        with self._lock,self._connect() as db:
            row=db.execute('SELECT status FROM steps WHERE task_id=? AND step_id=?',(task_id,step_id)).fetchone()
            if row and row[0]=='committed':raise ValueError('Committed step cannot be executed twice')
            db.execute("""INSERT INTO steps(task_id,step_id,tool,args_digest,idempotency_key,status,verification,attempts,updated)
                VALUES(?,?,?,?,?,'started','',1,?) ON CONFLICT(task_id,step_id)
                DO UPDATE SET status='started', attempts=attempts+1,updated=excluded.updated""",
                (task_id,step_id,tool,args_digest,idempotency_key,time.time()))

    def step_finished(self,task_id:str,step_id:str,status:str,verification:str)->None:
        if status not in ('committed','failed','skipped'):
            raise ValueError('Unknown step completion state')
        if verification not in ('verified','unverified','failed','needs_review'):
            raise ValueError('Invalid verification evidence')
        if status=='committed' and verification!='verified':
            raise ValueError('Cannot commit a step without independent verification')
        with self._lock,self._connect() as db:
            result=db.execute('UPDATE steps SET status=?,verification=?,updated=? WHERE task_id=? AND step_id=? AND status=?',
                              (status,verification,time.time(),task_id,step_id,'started'))
            if result.rowcount!=1:raise ValueError('Step must be started before completion')

    def steps(self,task_id:str)->list[dict[str,Any]]:
        with self._lock,self._connect() as db:
            rows=db.execute('SELECT step_id,tool,args_digest,idempotency_key,status,verification,attempts FROM steps WHERE task_id=? ORDER BY updated',(task_id,)).fetchall()
        return [dict(zip(('step_id','tool','args_digest','idempotency_key','status','verification','attempts'),row)) for row in rows]

    def get(self, id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute('SELECT payload FROM tasks WHERE id=?', (id,)).fetchone()
        return json.loads(row[0]) if row else None

    def recent(self, limit: int = 12) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute('SELECT payload FROM tasks ORDER BY updated DESC LIMIT ?',
                              (min(60, max(1, limit)),)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def interrupt_stale(self) -> int:
        """Previous-process active tasks cannot still be approved or running."""
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id, payload FROM tasks WHERE status IN ('planning','running','approval')").fetchall()
            for id, payload in rows:
                value = json.loads(payload)
                value.update(status='interrupted', phase='verify',
                             message='Previous BARQ process ended. Reobserve and request explicit continuation.')
                db.execute('UPDATE tasks SET status=?, payload=?, updated=? WHERE id=?',
                           ('interrupted', json.dumps(value, ensure_ascii=False), time.time(), id))
            return len(rows)
