"""SQLite policy: transactions own and close their connections deterministically.

The stdlib connection context manager commits/rolls back but does NOT close.
Keeping that default left Windows self-test databases locked until a later GC.
"""
import sqlite3


class Connection(sqlite3.Connection):
    def __exit__(self,exc_type,exc_value,traceback):
        try:
            return super().__exit__(exc_type,exc_value,traceback)
        finally:
            self.close()


def connect(database, *args, **kwargs):
    kwargs.setdefault('timeout', 15.0)
    kwargs.setdefault('factory',Connection)
    db=sqlite3.connect(database, *args, **kwargs)
    try:
        db.execute('PRAGMA busy_timeout=15000')
        # Read-only SQLite databases cannot change journal_mode. Preserve their usability.
        if not str(database).startswith('file:') or 'mode=ro' not in str(database):
            db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
    except BaseException:
        db.close()
        raise
    return db
