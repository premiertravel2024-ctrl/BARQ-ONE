from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from workspace import manager as work


def test_stale_editor_cannot_preview_over_newer_disk(tmp_path):
    file=tmp_path/'app.py';file.write_text('value = 1\n')
    version=work.snapshot(str(tmp_path),'app.py')['revision']
    file.write_text('value = 2\n')
    with pytest.raises(work.FileConflict):work.propose(str(tmp_path),'app.py','value = 3\n',version)
    assert file.read_text()=='value = 2\n'


def test_empty_file_created_after_preview_is_a_conflict(tmp_path):
    proposed=work.propose(str(tmp_path),'new.py','print(1)\n','missing')
    (tmp_path/'new.py').write_text('')
    with pytest.raises(work.FileConflict):work.apply(proposed['approval_id'],True)
    assert (tmp_path/'new.py').read_text()==''


def test_revision_tracks_raw_windows_newlines(tmp_path):
    file=tmp_path/'app.py';file.write_bytes(b'print(1)\r\n')
    before=work.snapshot(str(tmp_path),'app.py')
    assert before['content']=='print(1)\n'
    preview=work.propose(str(tmp_path),'app.py','print(2)\n',before['revision'])
    file.write_bytes(b'print(1)\n')
    with pytest.raises(work.FileConflict):work.apply(preview['approval_id'],True)


def test_api_snapshots_scope_and_conflict_status(tmp_path):
    from api import app
    file=tmp_path/'app.py';file.write_text('print(1)\n')
    with TestClient(app) as client:
        first=client.get('/v1/workspace/file',params={'workspace':str(tmp_path),'path':'app.py'}).json()
        response=client.post('/v1/workspace/snapshots',json={'workspace':str(tmp_path),'paths':['app.py','deleted.py','../outside.py','.env']})
        assert response.status_code==200
        snapshots=response.json()['files'];assert snapshots[0]['revision']==first['revision']
        assert snapshots[1]['exists'] is False
        assert all('error' in item and 'content' not in item for item in snapshots[2:])
        assert client.post('/v1/workspace/snapshots',json={'workspace':str(tmp_path),'paths':['app.py']*19}).status_code==422
        file.write_text('print(2)\n')
        stale=client.post('/v1/workspace/edit/preview',json={'workspace':str(tmp_path),'path':'app.py','content':'print(3)\n','expected_revision':first['revision']})
        assert stale.status_code==409
        current=work.snapshot(str(tmp_path),'app.py')
        preview=client.post('/v1/workspace/edit/preview',json={'workspace':str(tmp_path),'path':'app.py','content':'print(3)\n','expected_revision':current['revision']}).json()
        saved=client.post('/v1/workspace/edit/apply',json={'approval_id':preview['approval_id'],'confirmed':True}).json()
        assert saved['workspace']==str(tmp_path) and saved['revision']==work.snapshot(str(tmp_path),'app.py')['revision']
        assert file.read_text()=='print(3)\n'


def test_diagnostics_returns_actual_syntax_line(tmp_path):
    from coding.diagnostics import diagnose
    (tmp_path/'broken.py').write_text('value = 1\ndef broken(:\n    pass\n')
    report=diagnose(str(tmp_path))
    assert report['syntax_errors'][0]['line']==2


def test_workspace_frontend_preserves_drafts_and_conflicts():
    from tests.test_chat_smoke_launcher_regression import run_smoke
    result=run_smoke(Path(__file__).resolve().parents[1]/'frontend/tests/workspace-sync.ts')
    assert result.returncode==0,result.stdout+'\n'+result.stderr
