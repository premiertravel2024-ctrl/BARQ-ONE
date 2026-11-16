from core.sqlite import connect as barq_sqlite_connect
import sqlite3,hashlib,json,threading
from contextlib import contextmanager


class Cache:
    def __init__(self,path='router_cache.sqlite3'):
        self.path=path
        self._lock=threading.RLock()
        self._closed=False
        self._memory=barq_sqlite_connect(path,check_same_thread=False) if str(path)==':memory:' else None
        with self._connection() as db:
            db.execute('create table if not exists answers (k text primary key, v text)')

    @contextmanager
    def _connection(self):
        with self._lock:
            if self._closed:raise sqlite3.ProgrammingError('Cannot operate on a closed cache')
            if self._memory is None:
                # No persistent file handle survives an operation or app shutdown.
                with barq_sqlite_connect(self.path) as db:yield db
            else:
                # An in-memory cache needs one connection for its lifetime.
                try:yield self._memory
                except BaseException:
                    self._memory.rollback();raise
                else:self._memory.commit()

    def close(self):
        with self._lock:
            if self._memory is not None:
                self._memory.close();self._memory=None
            self._closed=True
    def key(self,messages,model='auto',local=False):
        raw=json.dumps([messages,model,local],ensure_ascii=False,sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()
    def get(self,key):
        with self._connection() as db:
            r=db.execute('select v from answers where k=?',(key,)).fetchone()
        return json.loads(r[0]) if r else None
    def put(self,key,value):
        with self._connection() as db:
            db.execute('insert or replace into answers values (?,?)',(key,json.dumps(value,ensure_ascii=False)))
