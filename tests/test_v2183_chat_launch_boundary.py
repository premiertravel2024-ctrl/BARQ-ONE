"""Long project requests must never become truncated desktop launch commands."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import launcher.api as launch
from agent.task_intent import classify_task


@pytest.mark.parametrize('tail', [' تابع بناء البرنامج واختبره.'*20, '\n'+('ا'*300)])
def test_chat_launch_does_not_execute_a_prefix_of_a_long_message(monkeypatch,tail):
    def no_resolver():
        raise AssertionError('Long chat text must not reach the launcher resolver')
    monkeypatch.setattr(launch,'resolver',no_resolver)
    monkeypatch.setattr(launch,'launcher_settings',lambda:{'enabled':True})
    assert launch.local_chat_launch([{'role':'user','content':'افتح يوتيوب'+tail}]) is None


def test_launcher_api_exposes_its_real_text_limit():
    app=FastAPI();app.include_router(launch.router)
    response=TestClient(app).post('/v1/launch/resolve',json={'text':'افتح '+('س'*240),'source':'text','query_only':False})
    assert response.status_code==422
    assert response.json()['detail'][0]['loc']==['body','text']
    assert response.json()['detail'][0]['type']=='string_too_long'


@pytest.mark.parametrize('retry',['حاول','حاول تاني','جرّب','جرب تاني','retry'])
def test_retry_uses_the_same_chat_project_and_still_requires_approval(retry):
    goal='برق عاوزك تبنيلي برنامج Windows كامل اسمه TOFU Desktop Buddy.'
    intent=classify_task(retry,[goal])
    assert intent and intent['kind']=='coding'
    assert goal in intent['goal']
    assert intent['requires_approval'] is True
    assert classify_task(retry) is None
    assert classify_task(retry,[goal,'ازيك يا برق']) is None
