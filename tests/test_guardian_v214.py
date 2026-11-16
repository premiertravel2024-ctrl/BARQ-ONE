from core.version import VERSION
"""BARQ Guardian regression coverage; fake projects, no network or cloud calls."""
import json
import os
from pathlib import Path
from fastapi.testclient import TestClient
from studio.guardian import (project_health,dependency_status,build_readiness,
                             checkpoints,debug_guidance)
from studio.runtime_monitor import inspect_pid
from workspace import manager as work
from core.paths import state_file
from api import app


def test_health_marks_unrun_tests_and_smoke_as_unknown(tmp_path):
    (tmp_path / 'sample.py').write_text("print('ok')\n", encoding='utf-8')
    report=project_health(str(tmp_path))
    assert report['score'] is None
    assert report['security']['checked']>=1
    assert {c['id']:c['status'] for c in report['categories']}['tests']=='unknown'
    assert next(c for c in report['build']['checks'] if c['name']=='Full test suite')['status']=='unknown'


def test_security_findings_generate_plan_not_a_write(tmp_path):
    (tmp_path / 'bad.py').write_text('eval(input())\n',encoding='utf-8')
    report=project_health(str(tmp_path))
    findings=report['security']['findings']
    assert findings
    plan=debug_guidance(str(tmp_path),findings[0]['id'])
    assert plan['requires_approval'] is True and plan['applied'] is False
    assert (tmp_path / 'bad.py').read_text()=='eval(input())\n'


def test_dependency_audit_is_inventory_only_and_offline(tmp_path):
    (tmp_path/'requirements.txt').write_text('requests==2.0.0\n')
    status=dependency_status(str(tmp_path))
    assert status['status']=='unknown' and 'requirements.txt' in status['manifests']
    assert 'لم يتم الاتصال' in status['note_ar']


def test_restore_list_is_scoped_to_workspace_and_hides_content(tmp_path,monkeypatch):
    import tempfile
    alternate=tmp_path/'other';alternate.mkdir()
    target=tmp_path/'current';target.mkdir()
    (target/'main.py').write_text('before\n',encoding='utf-8')
    (alternate/'main.py').write_text('secret content\n',encoding='utf-8')
    backup=tmp_path/'backups';backup.mkdir()
    monkeypatch.setattr('studio.guardian.state_file', lambda _: backup)
    one='a'*32;two='b'*32
    (backup/(one+'.json')).write_text(json.dumps({'workspace':str(target),'path':'main.py','before':'before\n','after':'after\n'}))
    (backup/(two+'.json')).write_text(json.dumps({'workspace':str(alternate),'path':'main.py','before':'secret content\n','after':''}))
    result=checkpoints(str(target))
    assert len(result['checkpoints'])==1
    assert result['checkpoints'][0]['id']==one
    assert 'content' not in str(result)


def test_runtime_rejects_invalid_pid(tmp_path):
    try: inspect_pid(str(tmp_path),0)
    except ValueError: pass
    else: raise AssertionError('invalid PID was accepted')


def test_guardian_api_is_manual_and_read_only(tmp_path):
    (tmp_path/'main.py').write_text('print(1)\n')
    client=TestClient(app)
    response=client.get('/v1/studio/guardian/health',params={'workspace':str(tmp_path)})
    assert response.status_code==200,response.text
    data=response.json()
    assert data['score'] is None and data['workspace_name']==tmp_path.name
    assert client.get('/v1/studio/guardian/checkpoints',params={'workspace':str(tmp_path)}).status_code==200
    assert not (tmp_path/'main.py').read_text().startswith('UPDATED')


def test_bundled_ui_files_contain_guardian_marker_and_do_not_remove_tools():
    root=Path(__file__).resolve().parents[1]
    ts=(root/'frontend/src/components/workspace/WorkspaceStudio.tsx').read_text()
    assert f'v{VERSION}-build-gated-ui' in ts and 'GuardianDashboard' in ts
    for token in ('WorkspaceTools','LiveCodePanel','PreviewPanel','computer','build','github'):
        assert token in ts
    builder=(root/'scripts/build_windows.ps1').read_text()
    assert "npm run build" in builder and f'v{VERSION}-build-gated-ui' in builder
    assert 'Packaged .exe self-test PASSED' in builder
