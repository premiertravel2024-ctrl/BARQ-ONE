import base64
import hashlib
import json

import httpx
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core import app_updates


def manifest(key, payload):
    raw = json.dumps(payload).encode()
    return json.dumps({
        'payload': base64.b64encode(raw).decode(),
        'signature': base64.b64encode(key.sign(raw)).decode(),
    }).encode()


def release_fields(body):
    return dict(schema=1, product='BARQ ONE', platform='windows-x64', version='2.41.2',
                size=len(body), sha256=hashlib.sha256(body).hexdigest(), notes='New release')


def test_release_signature_and_version_order():
    key = Ed25519PrivateKey.generate()
    pinned = key.public_key().public_bytes_raw()
    payload = release_fields(b'MZinstaller')
    release = app_updates.Release.verify(manifest(key, payload), pinned)
    assert release.path == '/releases/2.41.2/BARQ_Setup_2.41.2.exe'
    with pytest.raises(InvalidSignature):
        app_updates.Release.verify(manifest(Ed25519PrivateKey.generate(), payload), pinned)
    with pytest.raises(ValueError):
        app_updates.Release.verify(manifest(key, dict(payload, version='../setup')), pinned)
    assert app_updates.version_key('2.41.11') > app_updates.version_key('2.41.2')


def test_download_rejects_tampering_and_only_commits_verified_data(monkeypatch, tmp_path):
    expected = b'MZinstaller'
    key = Ed25519PrivateKey.generate()
    pinned = key.public_key().public_bytes_raw()
    channel = app_updates.Channel('https://updates.example', pinned)
    release = app_updates.Release.verify(manifest(key, release_fields(expected)), pinned)
    data = b'MZwrong!!!!'
    client = httpx.Client

    def create_client(**kwargs):
        def respond(request):
            assert request.url.host == 'updates.example' and request.url.path == release.path
            return httpx.Response(200, content=data)
        return client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(app_updates.httpx, 'Client', create_client)
    with pytest.raises(ValueError):
        app_updates.download_release(channel, release, tmp_path)
    assert list(tmp_path.iterdir()) == []
    data = expected
    assert app_updates.download_release(channel, release, tmp_path).read_bytes() == expected
