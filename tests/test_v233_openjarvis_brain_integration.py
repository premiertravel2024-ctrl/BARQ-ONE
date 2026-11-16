"""OpenJarvis ideas transplanted into BARQ's native planner/mission/router.

Regression checks are intentionally local; no model network, OS-wide access,
process invocation, user file indexing, or permission bypass is needed.
"""
import json
from pathlib import Path

import pytest

from agent.orchestrator import ACTIONS, parse_plan, relevant_tools
from mission.tracking import (
    check_action_loop, remember_approved_action, remembered_actions, start, load_project,
)
from monitor.health import Health
from router.context import select_context


def test_egyptian_and_english_skill_aliases_require_available_catalog():
    result=parse_plan(json.dumps({'reason':'inspect','steps':[{'tool':'دور_في_الكود','args':{'phrase':'BAD'}}],
                                  'answer':'هيجهز البحث'}),{'code_search'})
    assert result['steps'][0]['tool']=='code_search'
    with pytest.raises(ValueError):
        parse_plan(json.dumps({'steps':[{'tool':'دور_في_الكود','args':{'phrase':'BAD'}}]}),{'code_check'})
    with pytest.raises(ValueError):
        parse_plan(json.dumps({'steps':[{'tool':'dangerous_shell','args':{}}]}),set(ACTIONS))
    assert 'code_search' in relevant_tools('برق دور في الكود على دالة الحساب',list(ACTIONS))
    assert 'project_build' in relevant_tools('ابني البرنامج EXE',list(ACTIONS))


def test_workflow_memory_is_hashed_local_and_does_not_save_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'data'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    goal='عايز أشغّل اختبارات مشروع مهم'
    sensitive='C:/Users/SECRET_PERSON/Documents/private_project.py'
    assert not remembered_actions(str(workspace),goal)['approved_actions']
    assert remember_approved_action(str(workspace),goal,None,'code_check',
                                    {'path':sensitive},True)
    remembered=remembered_actions(str(workspace),goal)
    assert remembered['approved_actions'][0]['tool']=='code_check'
    assert remembered['approved_actions'][0]['success'] is True
    files=list((tmp_path/'data'/'missions'/'workflow-actions').glob('*.json'))
    assert len(files)==1
    raw=files[0].read_text(encoding='utf-8')
    assert sensitive not in raw and 'SECRET_PERSON' not in raw and goal not in raw
    assert len(remembered_actions(str(workspace),'طلب مختلف')['approved_actions'])==0
    # A preview is not actually a saved edit and never enters the action log.
    assert remember_approved_action(str(workspace),goal,None,'workspace_edit',{'path':sensitive},True) is False
    assert len(remembered_actions(str(workspace),goal)['approved_actions'])==1


def test_persisted_project_checkpoints_preserve_goals_and_check_state(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'data'))
    workspace=tmp_path/'workspace';project=workspace/'calc';project.mkdir(parents=True)
    start(str(workspace),'calc','desktop_python','ابنيلي آلة حاسبة', ['main.py'])
    assert remember_approved_action(str(workspace),'ابنيلي آلة حاسبة','calc',
                                    'code_check',{'path':'calc/main.py'},True,'revision-1')
    # Reloaded from disk after a new in-memory scope.
    assert load_project(str(workspace),'calc')['approved_actions'][0]['tool']=='code_check'
    recalled=remembered_actions(str(workspace),'ابنيلي آلة حاسبة','calc')
    assert recalled['goal']=='ابنيلي آلة حاسبة'
    assert recalled['files'][0]['path']=='calc/main.py'
    assert recalled['approved_actions'][0]['success'] is True


def test_loop_guard_is_revision_aware_and_fails_closed_after_retries(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'data'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    goal='اختبر المشروع'
    for _ in range(2):
        assert check_action_loop(str(workspace),goal,None,'run_tests',{},'rev-a') is None
        remember_approved_action(str(workspace),goal,None,'run_tests',{},False,'rev-a')
    assert 'فشلت' in check_action_loop(str(workspace),goal,None,'run_tests',{},'rev-a')
    assert check_action_loop(str(workspace),goal,None,'run_tests',{},'rev-b') is None


def test_loop_guard_blocks_repetitive_success_and_ping_pong(tmp_path,monkeypatch):
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'data'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    goal='استكشف المشروع'
    for _ in range(3):
        remember_approved_action(str(workspace),goal,None,'workspace_list',{'path':''},True,'a')
    assert 'اتكررت' in check_action_loop(str(workspace),goal,None,'workspace_list',{'path':''},'a')
    goal2='مهمة مختلفة'
    for name in ['project_map','workspace_list']*3:
        remember_approved_action(str(workspace),goal2,None,name,{},True,'x')
    assert 'حلقة' in check_action_loop(str(workspace),goal2,None,'project_map',{},'x')


def test_learned_routing_is_per_task_bounded_and_persistent(tmp_path):
    path=tmp_path/'model-health.json'
    h=Health(str(path))
    for _ in range(9):h.report('ollama/coder',True,latency=0.35,task='coding')
    for _ in range(5):h.report('ollama/coder',False,task='simple')
    assert h.task_adjustment('ollama/coder','coding')>0
    assert h.task_adjustment('ollama/coder','simple')<0
    h.report_task_result('ollama/coder','coding',True)
    h.report_task_result('ollama/coder','coding',True)
    assert Health(str(path)).task_adjustment('ollama/coder','coding')>=h.task_adjustment('ollama/coder','simple')
    assert 'task_outcomes' in json.loads(path.read_text())['ollama/coder']
    assert 'verified_outcomes' in json.loads(path.read_text())['ollama/coder']
    assert h.task_adjustment('new/unseen','coding')==0


def test_local_context_retrieval_keeps_real_old_check_evidence():
    messages=[{'role':'system','content':'do not invent tests'},
              {'role':'assistant','content':'an old pytest report: FAIL for network test, needs fix '+('x'*900)},
              *[{'role':'assistant','content':'unrelated chatter '+str(i)+' '+('z'*900)} for i in range(14)],
              {'role':'user','content':'ازاي أصلح اختبار pytest failed؟'}]
    selected,omitted=select_context(messages,context_window=2048)
    assert omitted>0
    assert selected[0]['role']=='system'
    assert selected[-1]['role']=='user'
    assert any('pytest report' in m['content'] for m in selected)


def test_colloquial_device_intents_do_not_autorun_or_convert_capability_questions():
    from agent.task_intent import classify_task
    assert classify_task('دورلي على فيلم في الجهاز')['kind']=='computer'
    assert classify_task('هاتلي درجة حرارة المعالج')['kind']=='computer'
    assert classify_task('هو تقدر تدور في الجهاز؟') is None
    assert classify_task('ما تفتحش حاجة من الجهاز') is None


def test_verified_execution_evidence_alone_influences_local_routing(tmp_path):
    health=Health(str(tmp_path/'health.json'))
    assert health.task_adjustment('ollama/coder','coding')==0
    health.report_task_result('ollama/coder','coding',False)
    health.report_task_result('ollama/coder','coding',False)
    assert health.task_adjustment('ollama/coder','coding')<0


@pytest.mark.asyncio
async def test_planner_recalls_verified_actions_without_executing_anything(tmp_path,monkeypatch):
    from agent import orchestrator
    monkeypatch.setenv('AI_ROUTER_DATA_DIR',str(tmp_path/'data'))
    workspace=tmp_path/'workspace';workspace.mkdir()
    goal='افحص المشروع وحاول تصلح الكود'
    remember_approved_action(str(workspace),goal,None,'project_map',{},True)
    class Planner:
        async def run(self,messages,**kwargs):
            prompt=messages[0]['content']
            assert 'APPROVED ACTION CHECKPOINTS' in prompt
            assert 'project_map' in prompt
            assert 'RELEVANT TOOL CANDIDATES' in prompt
            return {'content':json.dumps({'reason':'inspect','steps':[{'tool':'workspace_list','args':{}}],
                                          'answer':'هراجع الملفات'}),'model':'ollama/test-model'}
    result=await orchestrator.plan(Planner(),str(workspace),[{'role':'user','content':goal}],task_goal=goal)
    assert result['plan']['steps'][0]['tool']=='workspace_list'
    assert result['plan_id'] in orchestrator.PENDING
    # Planning is never an authorization for a filesystem change.
    assert not (workspace/'new-file.py').exists()
    orchestrator.PENDING.pop(result['plan_id'],None)
