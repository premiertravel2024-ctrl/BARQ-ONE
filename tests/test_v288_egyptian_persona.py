"""Stable BARQ product identity independent of whichever model is selected."""
import pytest
from fastapi.testclient import TestClient
from core.persona import PRODUCT_IDENTITY, instant_identity_reply, with_identity
from brain.coordinator import Brain
from types import SimpleNamespace
from unittest.mock import AsyncMock


def reply(text):
    return instant_identity_reply([{'role':'user','content':text}])


@pytest.mark.parametrize('question', [
    'مين اللي طورك؟', 'مين عملك', 'مين مطور برق', 'who developed you',
])
def test_creator_is_canonical(question):
    assert ('أشرف محمد' in reply(question) or 'Ashraf Mohamed' in reply(question))


@pytest.mark.parametrize('question', [
    'اسمك جه منين؟', 'ليه اتسميت برق؟', 'where did your name come from',
])
def test_cars_egyptian_name_origin(question):
    result=reply(question)
    assert 'Cars' in result
    assert 'برق بنزين' in result
    assert 'المصرية' in result or 'Egyptian' in result


@pytest.mark.parametrize('question', ['انت مصري؟','انت منين','are you egyptian','إنت مين؟'])
def test_egyptian_dialect_persona(question):
    result=reply(question)
    assert 'مصري' in result or 'Egyptian' in result


def test_model_prompts_all_get_creator_dialect_and_origin():
    source=[{'role':'user','content':'صلّح مشكلة في كود Python'}]
    wrapped=with_identity(source)
    assert wrapped[0]['role']=='system'
    for key in ('Ashraf Mohamed','أشرف محمد','Cars','برق بنزين','مصري'):
        assert key in wrapped[0]['content']
    assert wrapped[-1]==source[-1] and wrapped[-1] is not source[-1]
    assert with_identity(source,voice_mode=True)[0]['content'].endswith('Avoid excessive technical symbols in spoken replies.')


@pytest.mark.parametrize('normal_request', [
    'ترجم النص بدقة مع الحفاظ على المعنى.',
    'صمم لوجو لبرنامج برق',
    'برق، نفذ التعديل في ملف Cars.py',
    'اكتب قصة عن شخص اسمه أشرف محمد',
    'ترجم: مين اللي طورك؟',
    'عاوز تشرح فيلم Cars الأول',
])
def test_persona_faq_does_not_hijack_normal_tasks(normal_request):
    assert reply(normal_request) is None


@pytest.mark.asyncio
async def test_brain_identity_runs_offline_and_does_not_call_models():
    engine=SimpleNamespace(run=AsyncMock(side_effect=AssertionError('cloud called')),
                           stream_run=AsyncMock(side_effect=AssertionError('stream called')))
    brain=Brain(engine)
    result=await brain.run([{'role':'user','content':'مين اللي طورك؟'}],model='auto')
    assert result['model']=='BARQ-AI/local'
    assert 'أشرف محمد' in result['content']
    stream=[ev async for ev in brain.stream([{'role':'user','content':'اسمك جه منين؟'}],model='auto')]
    assert any('Cars' in ev.get('content','') for ev in stream)
    engine.run.assert_not_called()
    engine.stream_run.assert_not_called()


def test_legacy_and_openai_compatible_endpoints_share_canonical_persona(monkeypatch):
    import api
    async def should_not_call(*args,**kwargs):raise AssertionError('model invocation on identity FAQ')
    monkeypatch.setattr(api.engine,'run',should_not_call)
    with TestClient(api.app) as client:
        for uri in ('/v1/router/chat','/v1/chat/completions'):
            result=client.post(uri,json={'messages':[{'role':'user','content':'مين اللي طورك؟'}]})
            assert result.status_code==200
            assert 'أشرف محمد' in (result.json().get('content') or result.json()['choices'][0]['message']['content'])
        stream=client.post('/v1/router/chat/stream',json={'messages':[{'role':'user','content':'اسمك جه منين؟'}]})
        assert 'برق بنزين' in stream.text
        assert 'event: done' in stream.text


def test_brand_identity_is_a_product_fact_not_claim_of_real_movie_character():
    assert PRODUCT_IDENTITY['creator_en']=='Ashraf Mohamed'
    assert 'independent' in PRODUCT_IDENTITY['film_relationship']


def test_response_validator_rejects_provider_self_intro_and_foreign_greeting():
    brain=Brain(SimpleNamespace())
    messages=[{'role':'user','content':'ازيك يا برق'}]
    with pytest.raises(ValueError,match='upstream model'):
        brain._check_reply('أنا ChatGPT، إزاي أساعدك؟',messages)
    with pytest.raises(ValueError,match='non-Egyptian'):
        brain._check_reply('أهلاً بك! أنا مستعد تمامًا لمساعدتك.', messages)
    brain._check_reply('أيوه يا صاحبي، قولّي محتاج إيه؟', messages)
    # Quoted/translated material isn't subject to the colloquial output policy.
    brain._check_reply('أهلاً بك! أنا مستعد تمامًا لمساعدتك.', [{'role':'user','content':'ترجم نص الرسالة'}])
