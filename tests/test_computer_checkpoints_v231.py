import asyncio
import sqlite3
import pytest

from computer_control.state_store import TaskStateStore
from computer_control.executor.manager import Manager
from computer_control.safety.policy import Policy


def test_state_store_strips_private_tool_arguments_and_approvals(tmp_path):
    store=TaskStateStore(tmp_path/'tasks.sqlite3')
    store.save({'id':'task-one','goal':'open a window','model':'auto','status':'approval','phase':'execute',
                'pending':{'tool':'type_text','args':{'text':'SECRET-PASSWORD'}},
                'history':[{'tool':'click','status':'ok','result':'password-SECRET','args':{'token':'SECRET-TOKEN'},'verification':'observed_change'}]})
    loaded=store.get('task-one')
    assert loaded['status']=='approval' and loaded['history'][0]['tool']=='click'
    assert 'pending' not in loaded
    assert 'SECRET' not in str(loaded)


def test_unclean_shutdown_marks_interrupted_and_is_idempotent(tmp_path):
    store=TaskStateStore(tmp_path/'tasks.sqlite3')
    store.save({'id':'task-one','goal':'make folder','status':'running','phase':'execute'})
    store.save({'id':'task-two','goal':'view programs','status':'completed'})
    assert store.interrupt_stale()==1
    assert store.interrupt_stale()==0
    assert store.get('task-one')['status']=='interrupted'
    assert store.get('task-two')['status']=='completed'


def test_bounded_task_history(tmp_path):
    store=TaskStateStore(tmp_path/'tasks.sqlite3')
    for i in range(72):store.save({'id':f'job-{i:03}','goal':'view','status':'completed'})
    assert len(store.recent(200))==60
    assert store.get('job-000') is None


def test_explicit_continuation_required(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    store=TaskStateStore(tmp_path/'computer_control_checkpoints.sqlite3')
    store.save({'id':'task-old','goal':'inspect apps','status':'interrupted'})
    class Stub:pass
    instance=Manager(Stub(),policy=Policy(enabled=True),planner=Stub())
    with pytest.raises(ValueError,match='confirmation'):instance.continue_interrupted('task-old')
    with pytest.raises(ValueError,match='Only interrupted'):instance.continue_interrupted('nonexistent',confirmed=True)
    async def run():
        # No side effects; the new task may not start with a stale approval.
        result=instance.continue_interrupted('task-old',confirmed=True)
        assert result['id']!='task-old'
        assert result['pending'] is None and result['progress']==0
        instance.stop()
    asyncio.run(run())


def test_invalid_db_no_execution_on_persist_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path))
    class Stub:pass
    manager=Manager(Stub(),policy=Policy(enabled=True),planner=Stub())
    manager.state_store.path=tmp_path/'nonexistent'/'broken.sqlite3'
    with pytest.raises(OSError):manager.start('show windows',start_task=False)
    assert manager.current is None


def test_invalid_db_path_fails_closed_on_windows_branch(tmp_path, monkeypatch):
    """Guard must be platform-independent: sqlite errors differ on Windows."""
    from types import SimpleNamespace
    import computer_control.state_store as state_store_module

    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path))
    class Stub: pass
    manager = Manager(Stub(), policy=Policy(enabled=True), planner=Stub())
    manager.state_store.path = tmp_path / 'missing-directory' / 'broken.sqlite3'
    monkeypatch.setattr(state_store_module, 'os', SimpleNamespace(name='nt'))
    with pytest.raises(FileNotFoundError, match='checkpoint parent directory'):
        manager.start('show windows', start_task=False)
    assert manager.current is None
    manager.stop()


def test_db_parent_replaced_with_file_prevents_task_start(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR', str(tmp_path))
    class Stub: pass
    manager = Manager(Stub(), policy=Policy(enabled=True), planner=Stub())
    blocking_file = tmp_path / 'blocking-parent'
    blocking_file.write_text('not a directory', encoding='utf-8')
    manager.state_store.path = blocking_file / 'broken.sqlite3'
    with pytest.raises(NotADirectoryError, match='checkpoint parent'):
        manager.start('show windows', start_task=False)
    assert manager.current is None
    manager.stop()
