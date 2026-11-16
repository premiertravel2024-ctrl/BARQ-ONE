"""SQLite handles must close before Windows deletes isolated self-test state."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from core import sqlite as storage


def assert_closed(connection):
    # Keep a strong reference: garbage collection must not make this pass.
    with pytest.raises(sqlite3.ProgrammingError,match='closed'):
        connection.execute('SELECT 1')


def test_transaction_commits_then_closes_without_gc(tmp_path):
    path=tmp_path/'state.sqlite3'
    with storage.connect(path) as db:
        db.execute('CREATE TABLE values_table(value INTEGER)')
        db.execute('INSERT INTO values_table VALUES (42)')
    assert_closed(db)
    with storage.connect(path) as check:
        assert check.execute('SELECT value FROM values_table').fetchall()==[(42,)]
    assert_closed(check)


def test_transaction_rolls_back_then_closes_on_exception(tmp_path):
    path=tmp_path/'state.sqlite3'
    with storage.connect(path) as init:
        init.execute('CREATE TABLE values_table(value INTEGER UNIQUE)')
    with pytest.raises(sqlite3.IntegrityError):
        with storage.connect(path) as db:
            db.execute('INSERT INTO values_table VALUES (42)')
            db.execute('INSERT INTO values_table VALUES (42)')
    assert_closed(db)
    with storage.connect(path) as check:
        assert check.execute('SELECT COUNT(*) FROM values_table').fetchone()[0]==0


@pytest.mark.parametrize('store_name',['brain','history','quota','semantic','project','launcher','cache'])
def test_every_file_backed_store_releases_all_handles(tmp_path,monkeypatch,store_name):
    opened=[]
    native=sqlite3.connect
    def track(*args,**kwargs):
        db=native(*args,**kwargs);opened.append(db);return db
    monkeypatch.setattr(storage.sqlite3,'connect',track)
    if store_name=='brain':
        from brain.state import TaskStore
        store=TaskStore(tmp_path/'brain.sqlite3')
        task=store.begin('chat','coding','inspect',str(tmp_path),'runtime')
        store.event(task['id'],'check','verified')
        assert store.latest('chat')['events'][0]['label']=='verified'
    elif store_name=='history':
        from core.history import ConversationStore
        store=ConversationStore(tmp_path/'history.sqlite3')
        store.put('chat','title',[])
        assert store.get('chat')['title']=='title'
        assert len(store.list())==1
    elif store_name=='quota':
        from router.quota import QuotaManager
        store=QuotaManager(db_path=tmp_path/'quota.sqlite3')
        store.record('model',3)
        store.reconcile('model',3,4)
        assert store.remaining('model',10)==9
    elif store_name=='semantic':
        from command_network.semantic_cache import SemanticCache
        SemanticCache(path=tmp_path/'semantic.sqlite3')
    elif store_name=='project':
        from coding import project_state
        monkeypatch.setattr(project_state,'state_file',lambda _:tmp_path/'project.sqlite3')
        project_state.save_note(str(tmp_path),'local note')
        project_state.record(str(tmp_path),'code_check',True)
        assert project_state.note(str(tmp_path))['note']=='local note'
        assert project_state.recent(str(tmp_path))['actions'][0]['success']
    elif store_name=='launcher':
        from launcher.indexes import Index
        Index(path=tmp_path/'launcher.sqlite3')
    else:
        from cache.store import Cache
        cache=Cache(tmp_path/'cache.sqlite3')
        cache.put('key',{'content':'saved'})
        assert cache.get('key')=={'content':'saved'}
    assert opened
    for db in opened:assert_closed(db)


def test_cache_parallel_writes_and_reopen_preserve_data(tmp_path):
    from cache.store import Cache
    path=tmp_path/'cache.sqlite3'
    cache=Cache(path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda n:cache.put(str(n),{'value':n}),range(24)))
    reopened=Cache(path)
    assert [reopened.get(str(n))['value'] for n in range(24)]==list(range(24))


def _run_windows_sqlite_probe(tmp_path, *, inject_leak=False):
    """Prove SQLite cleanup deterministically, without booting the whole app.

    The frozen BARQ.exe --self-test later in build_windows.ps1 exercises real
    HTTP/React/voice startup. Mixing that expensive integration smoke with a
    unit test made the Windows pytest gate time out after 60 seconds.
    """
    root = Path(__file__).resolve().parents[1]
    report = tmp_path / ('leak.json' if inject_leak else 'report.json')
    script = root / 'scripts' / 'probe_sqlite_cleanup.py'
    cmd = [sys.executable, str(script), str(report)]
    if inject_leak:
        cmd.append('--inject-leak')
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=25)
    assert result.returncode == 0, (result.stdout + '\n' + result.stderr)
    assert report.is_file(), result.stdout + '\n' + result.stderr
    return json.loads(report.read_text(encoding='utf-8'))


def test_selftest_cleanup_obeys_windows_file_sharing_without_gc(tmp_path):
    report = _run_windows_sqlite_probe(tmp_path)
    assert report['status'] == 'ok' and report['cleanup_completed']
    assert report['sqlite_transactions_verified']


def test_selftest_cleanup_blocks_an_open_sqlite_handle(tmp_path):
    report = _run_windows_sqlite_probe(tmp_path, inject_leak=True)
    assert report['status'] == 'error'
    assert report['exception'] == 'PermissionError' and report['phase'] == 'cleanup'


def test_full_exe_smoke_still_runs_after_python_unit_tests():
    """The cheap unit probe must NOT replace the packaged-app smoke test."""
    source = (Path(__file__).resolve().parents[1] / 'scripts' / 'build_windows.ps1').read_text(encoding='utf-8')
    assert 'Smoke-testing the actual packaged Windows executable' in source
    assert "@('--self-test', $quotedReport)" in source
    assert "smoke_install.ps1" in source
    assert (Path(__file__).resolve().parents[1] / 'scripts' / 'smoke_install.ps1').is_file()


def test_selftest_cleanup_error_is_not_reported_as_success(tmp_path,monkeypatch):
    import desktop
    import tempfile
    original=tempfile.TemporaryDirectory
    directories=[]
    class FailsOnce(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);directories.append(self)
        def cleanup(self):
            raise PermissionError(32,'WinError 32: simulated locked file')
    monkeypatch.setattr(tempfile,'TemporaryDirectory',FailsOnce)
    monkeypatch.setattr(desktop,'bundled_health_check',lambda:{'status':'ok'})
    report=tmp_path/'report.json'
    try:
        assert desktop.write_self_test_report(str(report))==1
        data=json.loads(report.read_text())
        assert data['status']=='error' and data['exception']=='PermissionError'
        assert data['phase']=='cleanup'
    finally:
        for directory in directories:original.cleanup(directory)


def test_in_memory_cache_still_retains_entries_until_closed():
    from cache.store import Cache
    cache=Cache(':memory:')
    cache.put('one',{'value':1})
    assert cache.get('one')=={'value':1}
    connection=cache._memory
    cache.close()
    assert_closed(connection)
    with pytest.raises(sqlite3.ProgrammingError,match='closed'):
        cache.get('one')


def test_sqlite_initialization_failure_closes_connection(monkeypatch,tmp_path):
    class BrokenConnection:
        closed=False
        def execute(self,*args):raise sqlite3.OperationalError('simulated pragma failure')
        def close(self):self.closed=True
    db=BrokenConnection()
    monkeypatch.setattr(storage.sqlite3,'connect',lambda *args,**kwargs:db)
    with pytest.raises(sqlite3.OperationalError,match='simulated pragma failure'):
        storage.connect(tmp_path/'state.sqlite3')
    assert db.closed


def test_read_only_database_is_readable_and_connection_closes(tmp_path):
    path=tmp_path/'read only.sqlite3'
    with storage.connect(path) as writer:
        writer.execute('CREATE TABLE example(value INTEGER)')
        writer.execute('INSERT INTO example VALUES (7)')
    with storage.connect(path.as_uri()+'?mode=ro',uri=True) as reader:
        assert reader.execute('SELECT value FROM example').fetchone()[0]==7
    assert_closed(reader)
