from types import SimpleNamespace
from brain.coordinator import Brain
from brain.state import TaskStore
from agent.orchestrator import parse_plan,ACTIONS
import pytest,json

def test_old_test_pass_cannot_complete_new_saved_code(tmp_path):
    brain=Brain(SimpleNamespace(),TaskStore(tmp_path/'brain.db'))
    task=brain.store.begin('c','coding','ابني برنامج',str(tmp_path),brain.runtime_id)
    brain.store.evidence(task['id'],[{'tool':'run_tests','success':True}])
    brain.store.update(task['id'],saved_paths=['main.py'],checks_after_save=[])
    result=brain._attach(task['id'],{'answer':'done','results':[{'tool':'code_check','success':True}]})
    assert result['task_status']=='blocked'

def test_latest_failed_check_invalidates_old_success(tmp_path):
    brain=Brain(SimpleNamespace(),TaskStore(tmp_path/'brain.db'))
    task=brain.store.begin('c','coding','اختبر المشروع',str(tmp_path),brain.runtime_id)
    brain.store.evidence(task['id'],[{'tool':'run_tests','success':True},{'tool':'run_tests','success':False}])
    assert 'run_tests' not in brain.store.get(task['id'])['checks_after_save']
    assert brain._attach(task['id'],{'answer':'done'})['task_status']=='blocked'
    brain.store.evidence(task['id'],[{'tool':'run_tests','success':True}])
    assert brain._attach(task['id'],{'answer':'done'})['task_status']=='completed'

def test_environment_plan_must_name_project():
    with pytest.raises(ValueError,match='project'):
        parse_plan(json.dumps({'steps':[{'tool':'prepare_test_environment','args':{}}]}),set(ACTIONS))
