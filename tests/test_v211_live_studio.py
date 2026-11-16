"""BARQ Studio live generation must stream genuine tokens and never write silently."""
from pathlib import Path
from fastapi.testclient import TestClient
import api


def test_studio_stream_forwards_real_tokens_without_tools(monkeypatch):
    calls = []
    async def fake_stream(messages, model='auto', **kwargs):
        calls.append((messages, model))
        yield {'type':'routing', 'status':'اختيار النموذج'}
        yield {'type':'model', 'model':'ollama/test', 'provider':'ollama'}
        yield {'type':'token', 'content':'```python\nprint('}
        yield {'type':'token', 'content':'"hello")\n```'}
        yield {'type':'done', 'finish_reason':'stop'}
    monkeypatch.setattr(api.brain, 'stream', fake_stream)
    client=TestClient(api.app)
    response=client.post('/v1/studio/assistant/stream',json={
        'workspace':'','path':'','selection':'','include_file':False,
        'model':'auto','prompt':'اكتب كود بايثون',
    })
    assert response.status_code==200,response.text
    assert 'event: routing' in response.text
    assert 'event: token' in response.text
    assert 'print(' in response.text
    assert 'event: done' in response.text
    assert len(calls)==1
    assert calls[0][1]=='auto'
    assert 'api_key' not in response.text.lower()


def test_stream_only_on_explicit_post(monkeypatch):
    count=[]
    async def fake_stream(*args, **kwargs):
        count.append(True)
        yield {'type':'done'}
    monkeypatch.setattr(api.brain,'stream',fake_stream)
    client=TestClient(api.app)
    assert client.get('/v1/studio/assistant/stream').status_code==405
    assert not count


def test_studio_preview_does_not_write_without_approval(tmp_path):
    target=tmp_path/'widget.py'
    target.write_text('print(1)\n',encoding='utf-8')
    client=TestClient(api.app)
    response=client.post('/v1/workspace/edit/preview',json={
        'workspace':str(tmp_path), 'path':'widget.py','content':'print(2)\n'})
    assert response.status_code==200,response.text
    assert response.json()['changed']
    assert target.read_text(encoding='utf-8')=='print(1)\n'
    denied=client.post('/v1/workspace/edit/apply',json={
        'approval_id':response.json()['approval_id'],'confirmed':False})
    assert denied.status_code in (400,422)
    assert target.read_text(encoding='utf-8')=='print(1)\n'


def test_studio_rejects_escape_paths_before_model_call(tmp_path,monkeypatch):
    calls=[]
    async def fake_stream(*args,**kwargs):
        calls.append(True)
        yield {'type':'done'}
    monkeypatch.setattr(api.brain,'stream',fake_stream)
    client=TestClient(api.app)
    response=client.post('/v1/studio/assistant/stream',json={
        'workspace':str(tmp_path),'path':'../private.env','include_file':True,
        'model':'auto','prompt':'اقرأ هذا الملف'})
    assert response.status_code==400
    assert not calls
