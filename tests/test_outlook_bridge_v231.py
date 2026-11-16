import time
import pytest
from services.outlook_bridge import OutlookBridge


def test_unconfigured_does_not_claim_connected():
    bridge=OutlookBridge(app_id='')
    assert not bridge.status()['configured']
    with pytest.raises(RuntimeError,match='CLIENT_ID'):bridge.connect()
    with pytest.raises(RuntimeError,match='authorization'):bridge.inbox()


def test_outlook_metadata_minimal(monkeypatch):
    b=OutlookBridge(app_id='client')
    b._access_token='test-token';b._expires_at=time.monotonic()+30
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'value':[{'subject':'A title','bodyPreview':'DO NOT LEAK',
                 'from':{'emailAddress':{'address':'sender@example.com'}},
                 'receivedDateTime':'2026-10-31','isRead':True,'id':'opaque-secret-id'}]}
    calls=[]
    import httpx
    monkeypatch.setattr(httpx,'get',lambda *args,**kw:(calls.append((args,kw)),Response())[1])
    messages=b.inbox(10)['messages']
    assert messages==[{'subject':'A title','sender':'sender@example.com','received':'2026-10-31','is_read':True}]
    assert 'Mail.ReadBasic' in b.status()['permissions']
    assert calls[0][0][0].startswith('https://graph.microsoft.com/')
    assert 'body' not in calls[0][1]['params']['$select']
    assert not b.disconnect()['connected']


def test_token_expiration_blocks_request(monkeypatch):
    b=OutlookBridge(app_id='x');b._access_token='secret';b._expires_at=time.monotonic()-2
    with pytest.raises(RuntimeError):b.inbox()
    assert not b.status()['connected']
