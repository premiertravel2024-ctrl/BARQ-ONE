import json
from pathlib import Path
import pytest
from tools.registry import project_python,prepare_test_environment
from tests.test_v222_source_mission import ready_mission
from mission.tracking import load_project
from mission.validation import fingerprint,record_validation,next_validation

def test_project_interpreter_precedes_global(tmp_path):
    p=tmp_path/'.barq-venv/Scripts/python.exe';p.parent.mkdir(parents=True);p.touch()
    assert project_python(tmp_path)==str(p)

@pytest.mark.asyncio
async def test_dependency_install_requires_approval(tmp_path):
    with pytest.raises(ValueError,match='Approval'):await prepare_test_environment(str(tmp_path))
    assert not (tmp_path/'.barq-venv').exists()

def test_missing_pytest_proposes_setup_then_retries_same_test(tmp_path,monkeypatch):
    root=ready_mission(tmp_path,monkeypatch);workspace=str(root);digest=fingerprint(workspace,'app')
    record_validation(workspace,'app',{'tool':'run_tests','success':False,'result':json.dumps({'stderr':'python.exe: No module named pytest','exit_code':1})},digest)
    step=next_validation(workspace,'app',load_project(workspace,'app'))
    assert step['steps']==[{'tool':'prepare_test_environment','args':{'project':'app'}}]
    record_validation(workspace,'app',{'tool':'prepare_test_environment','success':False,'error':'offline'},digest)
    assert next_validation(workspace,'app',load_project(workspace,'app')) is None
    record_validation(workspace,'app',{'tool':'prepare_test_environment','success':True,'result':'installed'},digest)
    assert next_validation(workspace,'app',load_project(workspace,'app'))['steps'][0]['tool']=='run_tests'
