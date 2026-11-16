"""Product-name calls and language regression from the reported screenshot."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from brain.coordinator import Brain
from brain.state import TaskStore
from core.addressing import address_reply, command_without_address, expects_egyptian


def brain(tmp_path):
    return Brain(SimpleNamespace(run=AsyncMock(side_effect=AssertionError('A name call must not reach a model'))),TaskStore(tmp_path/'brain.sqlite3'))


@pytest.mark.parametrize('call',['برق','يا برق','برق؟','برق!','بَرْق','برق AI'])
@pytest.mark.asyncio
async def test_arabic_call_is_local_even_after_wrong_language_history(tmp_path,call):
    b=brain(tmp_path)
    messages=[{'role':'user','content':'ازيك'},{'role':'assistant','content':'سلام! واژه برق کاربردهای زیادی دارد.'},{'role':'user','content':call}]
    assert (await b.route(messages,'c'))['reply']=='أيوه، معاك. قولّي.'
    assert (await b.run(messages))['content']=='أيوه، معاك. قولّي.'
    events=[event async for event in b.stream(messages)]
    assert ''.join(e['content'] for e in events if e['type']=='token')=='أيوه، معاك. قولّي.'
    b.engine.run.assert_not_called()


@pytest.mark.parametrize('call',['BARQ','hey barq','barq ai?'])
def test_english_name_calls(call):
    assert address_reply(call)=="I'm here. What do you need?"


@pytest.mark.parametrize('text',['ما معنى البرق؟','اشرح البرق والرعد','ترجم كلمة برق إلى الفارسية','برق ورعد'])
def test_real_questions_are_not_swallowed_as_product_calls(text):
    assert address_reply(text) is None


def test_dialect_correction_does_not_request_persian():
    assert expects_egyptian([{'role':'user','content':'ليه بترد بالفارسي؟ اتكلم مصري'}])
    assert not expects_egyptian([{'role':'user','content':'ترجم كلمة برق إلى الفارسية'}])
    assert not expects_egyptian([{'role':'user','content':'رد بالإنجليزي'}])


@pytest.mark.asyncio
async def test_vocative_prefix_does_not_hide_a_desktop_command(tmp_path):
    b=brain(tmp_path)
    result=await b.route([{'role':'user','content':'يا برق، افتح Excel'}],'c')
    assert result['intent']['kind']=='computer'
    assert command_without_address('برق ورعد')=='برق ورعد'
    b.engine.run.assert_not_called()


@pytest.mark.asyncio
async def test_vocative_followup_uses_existing_task(tmp_path):
    b=brain(tmp_path)
    task=b.store.begin('c','coding','افحص المشروع',str(tmp_path),b.runtime_id)
    b.store.update(task['id'],status='blocked')
    result=await b.route([{'role':'user','content':'يا برق كمل'}],'c',str(tmp_path))
    assert result['intent']['goal']=='افحص المشروع'
    b.engine.run.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_language_is_rejected_before_visible_stream(tmp_path):
    calls=[]
    async def stream(messages,**kwargs):
        calls.append(messages)
        yield {'type':'model','model':'mock/free'}
        text='سلام! واژه برق کاربردهای زیادی دارد. لطفاً مشخص کنید منظورتان کدام مورد است تا بتوانم بیشتر راهنمایی کنم.' if len(calls)==1 else 'أنا برق، معاك. قولي عايزني أساعدك في إيه وهنكمل خطوة بخطوة.'
        for start in range(0,len(text),8):yield {'type':'token','content':text[start:start+8]}
        yield {'type':'done'}
    b=Brain(SimpleNamespace(stream_run=stream),TaskStore(tmp_path/'brain.sqlite3'))
    events=[event async for event in b.stream([{'role':'user','content':'عامل ايه؟'}])]
    answer=''.join(e['content'] for e in events if e['type']=='token')
    assert 'واژه' not in answer and 'أنا برق' in answer
    assert len(calls)==2
    assert events[-1]['type']=='done'


def test_screenshot_prompt_all_api_routes_are_local(tmp_path,monkeypatch):
    import api
    from fastapi.testclient import TestClient
    b=brain(tmp_path);monkeypatch.setattr(api,'brain',b)
    with TestClient(api.app) as client:
        payload={'conversation_id':'screenshot','messages':[{'role':'user','content':'برق'}]}
        assert client.post('/v1/brain/route',json=payload).json()['reply']=='أيوه، معاك. قولّي.'
        assert client.post('/v1/router/chat',json=payload).json()['content']=='أيوه، معاك. قولّي.'
        streamed=client.post('/v1/router/chat/stream',json=payload)
        assert 'أيوه، معاك. قولّي.' in streamed.text
        completion=client.post('/v1/chat/completions',json=payload).json()
        assert completion['choices'][0]['message']['content']=='أيوه، معاك. قولّي.'
    b.engine.run.assert_not_called()


def test_address_removal_preserves_paths_and_symbol_case():
    assert command_without_address(r'يا برق، افتح D:\MyProject\SourceFile.py')==r'افتح D:\MyProject\SourceFile.py'
    assert command_without_address('برق عدل MyFunction إلى OtherFunction')=='عدل MyFunction إلى OtherFunction'
