from pathlib import Path
from fastapi.testclient import TestClient
import pytest
import api
from coding import project_state


def test_memory_and_activity_are_local_and_metadata_only(tmp_path,monkeypatch):
    monkeypatch.setattr(project_state,'state_file',lambda _:tmp_path/'notes.sqlite3')
    workspace=tmp_path/'workspace';workspace.mkdir()
    assert project_state.note(str(workspace))['note']==''
    project_state.save_note(str(workspace),'Use the existing service layer.')
    assert project_state.note(str(workspace))['note']=='Use the existing service layer.'
    with pytest.raises(ValueError):project_state.save_note(str(workspace),'x'*6001)
    project_state.record(str(workspace),'code_check',True)
    project_state.record(str(workspace),'run_tests',False)
    entries=project_state.recent(str(workspace))['actions']
    assert [x['tool'] for x in entries]==['run_tests','code_check']
    assert entries[0]['success'] is False
    assert 'content' not in entries[0]


def test_project_memory_api_requires_valid_workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(project_state,'state_file',lambda _:tmp_path/'notes.sqlite3')
    workspace=tmp_path/'workspace';workspace.mkdir()
    with TestClient(api.app) as client:
        bad=client.get('/v1/coding/note',params={'workspace':str(tmp_path/'missing')})
        assert bad.status_code==400
        saved=client.put('/v1/coding/note',json={'workspace':str(workspace),'note':'Sample project note'})
        assert saved.status_code==200
        loaded=client.get('/v1/coding/note',params={'workspace':str(workspace)})
        assert loaded.json()['note']=='Sample project note'
        activity=client.get('/v1/coding/activity',params={'workspace':str(workspace)})
        assert activity.status_code==200
        assert activity.json()['actions']==[]


def test_activity_uses_insertion_order_with_identical_timestamps(tmp_path,monkeypatch):
    """SQLite rows written in one timer tick must return newest first on Windows."""
    monkeypatch.setattr(project_state,'state_file',lambda _:tmp_path/'notes.sqlite3')
    monkeypatch.setattr(project_state.time,'time',lambda:100.0)
    workspace=tmp_path/'workspace';workspace.mkdir()
    project_state.record(str(workspace),'code_check',True)
    project_state.record(str(workspace),'run_tests',False)
    assert [x['tool'] for x in project_state.recent(str(workspace))['actions']]==['run_tests','code_check']


def test_activity_retention_keeps_newest_rows_on_tied_timestamps(tmp_path,monkeypatch):
    monkeypatch.setattr(project_state,'state_file',lambda _:tmp_path/'notes.sqlite3')
    monkeypatch.setattr(project_state.time,'time',lambda:100.0)
    workspace=tmp_path/'workspace';workspace.mkdir()
    for idx in range(205):
        project_state.record(str(workspace),f'run_{idx}',True)
    output=project_state.recent(str(workspace),100)['actions']
    assert len(output)==100
    assert output[0]['tool']=='run_204'
    assert output[-1]['tool']=='run_105'
    with project_state._db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM agent_activity').fetchone()[0]==200
        assert conn.execute('SELECT MIN(rowid) FROM agent_activity').fetchone()[0]==6
