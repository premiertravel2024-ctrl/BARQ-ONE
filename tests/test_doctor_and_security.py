from fastapi.testclient import TestClient
from api import app
from core.doctor import report

def test_doctor_never_discloses_credentials(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','secret-must-not-be-displayed')
    result=report()
    assert result['providers']['GEMINI_API_KEY'] is True
    assert 'secret-must-not-be-displayed' not in str(result)
    assert isinstance(result['runtimes']['git'],bool)
    assert result['windows_build_available'] in (True,False)
    response=TestClient(app).get('/v1/system/doctor')
    assert response.status_code==200
    assert 'secret-must-not-be-displayed' not in response.text

def test_dns_rebinding_and_cross_site_mutations_blocked():
    client=TestClient(app)
    assert client.get('/health',headers={'Host':'evil.example'}).status_code==403
    assert client.post('/v1/conversations',headers={'Host':'evil.example'},json={}).status_code==403
    assert client.post('/v1/models/settings',headers={'Origin':'https://evil.example'},json={'provider':'groq','enabled':False}).status_code==403
    assert client.get('/health').status_code==200

def test_websocket_remote_host_denied():
    client=TestClient(app)
    from starlette.websockets import WebSocketDisconnect
    try:
        with client.websocket_connect('/v1/voice/live',headers={'Host':'evil.example'}):
            assert False,'remote host should be rejected'
    except WebSocketDisconnect as exc:
        assert exc.code==1008
