from __future__ import annotations
import base64
import os
from unittest.mock import patch
import httpx
import pytest
from voice.gemini import (validate_audio,VoiceError,extract_text,extract_audio,extract_interaction_audio,
                         synthesize_speech,transcribe_audio)

@pytest.fixture(autouse=True)
def isolated_test_voice_keys(monkeypatch):
    """Use only test-provided env keys, never Windows Credential Manager.

    Production secret precedence stays unchanged. This prevents local credentials
    from contaminating mocked HTTP assertions or leaking into test traces.
    """
    import core.secrets
    monkeypatch.setattr(core.secrets, 'get', lambda name: os.environ.get(name, ''))


def test_validate_audio_mime_and_limit():
    assert validate_audio(b'123','audio/webm;codecs=opus')=='audio/webm'
    with pytest.raises(VoiceError):validate_audio(b'hi','text/html')
    with pytest.raises(VoiceError):validate_audio(b'','audio/wav')
    with pytest.raises(VoiceError):validate_audio(b'0'*(8*1024*1024+1),'audio/wav')

def test_response_parsers():
    assert extract_text({'candidates':[{'content':{'parts':[{'text':'إزيك يا باشا'}]}}]})=='إزيك يا باشا'
    assert extract_text({'output_text':'صباح الفل'})=='صباح الفل'
    assert extract_text({'steps':[{'type':'model_output','content':[{'type':'text','text':'ازيك'},{'type':'text','text':'يا صاحبي'}]}]})=='ازيك يا صاحبي'
    raw=b'RIFF'+b'\0'*4+b'WAVE'+b'\0'*32
    assert extract_audio({'candidates':[{'content':{'parts':[{'inlineData':{'data':base64.b64encode(raw).decode(),'mimeType':'audio/wav'}}]}}]})[0]==raw
    with pytest.raises(VoiceError):extract_audio({'candidates':[]})

@pytest.mark.asyncio
async def test_tts_request_and_voice_constraints(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    audio=b'RIFF'+b'\0'*4+b'WAVE'+b'\0'*32
    async def handler(req):
        assert req.url.path == '/v1beta/interactions'
        assert req.headers['x-goog-api-key']=='test-key'
        import json
        j=json.loads(req.content)
        assert j['model']=='gemini-3.8-flash-lite-tts'
        assert j['generation_config']['speech_config'][0]['voice']=='Charon'
        assert 'Egyptian Arabic' in j['input'][0]['content'][0]['annotations'][0]['style']
        return httpx.Response(200,json={'steps':[{'type':'model_output','content':[{'type':'audio','data':base64.b64encode(audio).decode()}]}]})
    transport=httpx.MockTransport(handler)
    old=httpx.AsyncClient
    def make_client(*args,**kwargs):return old(*args,transport=transport,**kwargs)
    with patch('voice.gemini.httpx.AsyncClient',side_effect=make_client):
        result,mime=await synthesize_speech('صباح الفل')
    assert result==audio and mime=='audio/wav'
    with pytest.raises(VoiceError):await synthesize_speech('test',voice='Kore')

@pytest.mark.asyncio
async def test_stt_upload_and_delete(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    calls=[]
    def handler(req):
        calls.append((req.method,req.url.path))
        if req.url.path=='/upload/v1beta/files':
            assert req.headers['x-goog-upload-header-content-type']=='audio/webm'
            return httpx.Response(200,headers={'x-goog-upload-url':'https://generativelanguage.googleapis.com/upload/session-123'})
        if req.url.path=='/upload/session-123':
            assert req.content==b'fakewebm'
            return httpx.Response(200,json={'file':{'name':'files/audio123','uri':'https://generativelanguage.googleapis.com/v1beta/files/audio123'}})
        if req.url.path=='/v1beta/interactions':
            import json
            p=json.loads(req.content)
            assert p['model']=='gemini-3.5-transcribe'
            assert p['input'][0]['type']=='audio'
            assert p['input'][0]['mime_type']=='audio/webm'
            assert p['input'][0]['uri'].startswith('https://generativelanguage.googleapis.com/')
            return httpx.Response(200,json={'output_text':'اعمل مشروع جديد','steps':[{'type':'model_output','content':[{'type':'text','text':'اعمل مشروع جديد'}]}]})
        if req.method=='DELETE':return httpx.Response(200,json={})
        return httpx.Response(404)
    transport=httpx.MockTransport(handler)
    old=httpx.AsyncClient
    def make_client(*args,**kwargs):return old(*args,transport=transport,**kwargs)
    with patch('voice.gemini.httpx.AsyncClient',side_effect=make_client):
        result=await transcribe_audio(b'fakewebm','audio/webm;codecs=opus')
    assert result=='اعمل مشروع جديد'
    assert calls[-1]==('DELETE','/v1beta/files/audio123')

@pytest.mark.asyncio
async def test_no_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    with pytest.raises(VoiceError,match='GEMINI_API_KEY'):
        await synthesize_speech('اهلاً')

def test_interactions_audio_rejects_malformed_output():
    with pytest.raises(VoiceError):extract_interaction_audio({'steps':[]})
    with pytest.raises(VoiceError):extract_interaction_audio({'steps':[{'type':'model_output','content':[{'type':'audio','data':'***'}]}]})


@pytest.mark.asyncio
async def test_local_fallback_on_interactions_failure(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    import voice.offline
    async def local_fallback(audio):
        assert audio==b'fakewebm'
        return 'كلام عربي محلي'
    monkeypatch.setattr(voice.offline,'transcribe_local',local_fallback)
    def handler(req):
        if req.url.path=='/upload/v1beta/files':
            return httpx.Response(200,headers={'x-goog-upload-url':'https://generativelanguage.googleapis.com/upload/session-123'})
        if req.url.path=='/upload/session-123':
            return httpx.Response(200,json={'file':{'name':'files/audio123','uri':'https://generativelanguage.googleapis.com/v1beta/files/audio123'}})
        if req.url.path=='/v1beta/interactions':
            return httpx.Response(404,json={'error':{'message':'not found'}})
        if req.method=='DELETE':return httpx.Response(200,json={})
        raise AssertionError(str(req.url))
    transport=httpx.MockTransport(handler)
    old=httpx.AsyncClient
    def make_client(*args,**kwargs):return old(*args,transport=transport,**kwargs)
    with patch('voice.gemini.httpx.AsyncClient',side_effect=make_client):
        assert await transcribe_audio(b'fakewebm','audio/webm')=='كلام عربي محلي'


@pytest.mark.asyncio
async def test_no_key_uses_opted_in_local_voice(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    import voice.offline
    async def local_fallback(audio):return 'تسجيل محلي'
    monkeypatch.setattr(voice.offline,'transcribe_local',local_fallback)
    assert await transcribe_audio(b'fakewebm','audio/webm')=='تسجيل محلي'
