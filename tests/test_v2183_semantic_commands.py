"""Semantic route coverage with a controlled provider; never runs desktop tools."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from brain.understanding import understand


@pytest.mark.asyncio
@pytest.mark.parametrize('wording',[
    'محتاج الزرار ده يبقى أحمر في المشروع',
    'ممكن اللون هنا يبقى أهدى شوية',
    'الحتة دي لسه بايظة، عاوزها مظبوطة',
    'عايز النتيجة اللي اتفقنا عليها بدل الوضع الحالي',
    'The button should use our agreed color instead',
])
async def test_unrecognized_words_reach_contextual_understanding(wording):
    meaning='Change the save button color in the selected project to red'
    engine=SimpleNamespace(run=AsyncMock(return_value={'content':json.dumps({
        'kind':'coding','goal':meaning,'question':'','task':'coding'})}))
    context=[{'role':'user','content':'بنتكلم عن زرار الحفظ في المشروع واللون الأحمر'}]
    result=await understand(engine,wording,[context[0]['content']],workspace='/selected',context=context)
    assert result['intent']['kind']=='coding'
    assert result['intent']['requires_approval'] is True
    assert meaning in result['intent']['goal'] and wording in result['intent']['goal']
    payload=json.loads(engine.run.call_args.args[0][1]['content'])
    assert payload['current_user_message']==wording
    assert payload['recent_conversation']==context
    assert payload['selected_workspace']=='/selected'
    assert callable(engine.run.call_args.kwargs['response_validator'])


@pytest.mark.asyncio
async def test_semantic_question_does_not_become_a_tool_plan():
    engine=SimpleNamespace(run=AsyncMock(return_value={'content':json.dumps({
        'kind':'chat','goal':'Explain a button style','question':'','task':'simple'})}))
    result=await understand(engine,'رأيك إيه في الشكل ده؟',[])
    assert result['intent'] is None and result['source']=='semantic'


@pytest.mark.asyncio
async def test_uncertain_target_asks_one_question_and_preserves_no_permissions():
    engine=SimpleNamespace(run=AsyncMock(return_value={'content':json.dumps({
        'kind':'clarify','goal':'','question':'تقصد زرار الحفظ ولا الإلغاء؟','task':'reasoning'})}))
    result=await understand(engine,'هو ده اللي محتاجه يبقى مختلف',[])
    assert result['intent'] is None
    assert result['clarification']=='تقصد زرار الحفظ ولا الإلغاء؟'


@pytest.mark.asyncio
async def test_semantic_request_reaches_real_project_planner_without_saving(tmp_path):
    from brain.coordinator import Brain
    from brain.state import TaskStore
    from agent import orchestrator
    source=tmp_path/'app.py';source.write_text("COLOR = 'blue'\n")
    wording='محتاج الزرار ده يبقى أحمر في المشروع'
    meaning='Change COLOR in app.py from blue to red'
    responses=[{'model':'test/reasoning','content':json.dumps({
        'kind':'coding','goal':meaning,'question':'','task':'coding'})},
        {'model':'test/coding','content':json.dumps({'reason':'Apply the requested button color',
            'steps':[{'tool':'code_replace','args':{'path':'app.py',
                'before':"COLOR = 'blue'",'after':"COLOR = 'red'"}}],
            'answer':'التعديل جاهز للمراجعة والموافقة.'})}]
    engine=SimpleNamespace(run=AsyncMock(side_effect=responses))
    brain=Brain(engine,TaskStore(tmp_path/'brain.sqlite3'))
    result=await brain.prepare(str(tmp_path),[{'role':'user','content':wording}],conversation_id='semantic-test')
    try:
        assert result['task_status']=='awaiting_approval'
        assert result['plan']['steps'][0]['tool']=='code_replace'
        record=brain.store.get(result['task_id'])
        assert meaning in record['goal'] and wording in record['goal']
        assert source.read_text()=="COLOR = 'blue'\n"
        with pytest.raises(ValueError,match='Approval'):
            await brain.execute(result['plan_id'],False,'semantic-test')
        assert source.read_text()=="COLOR = 'blue'\n"
    finally:
        orchestrator.PENDING.pop(result['plan_id'],None)
