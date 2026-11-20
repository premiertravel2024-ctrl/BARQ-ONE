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


def test_github_release_redirects_remain_on_trusted_hosts(monkeypatch, tmp_path):
    key = Ed25519PrivateKey.generate()
    body = b'MZinstaller'
    channel = app_updates.Channel(
        app_updates.usable_origin('https://github.com/example/barq-updates/'),
        key.public_key().public_bytes_raw(),
    )
    file = 'BARQ_Setup_2.41.2.exe'
    asset_host = 'release-assets.githubusercontent.com'
    client = httpx.Client

    def respond(request):
        path = request.url.path
        if request.url.host == 'github.com':
            if path.endswith('/latest/download/latest.json'):
                return httpx.Response(302, headers={
                    'location': '/example/barq-updates/releases/download/v2.41.2/latest.json',
                })
            assert path in (
                '/example/barq-updates/releases/download/v2.41.2/latest.json',
                '/example/barq-updates/releases/download/v2.41.2/' + file,
            )
            return httpx.Response(302, headers={
                'location': 'https://' + asset_host + '/asset/' + path.rsplit('/', 1)[-1],
            })
        assert request.url.host == 'release-assets.githubusercontent.com'
        return httpx.Response(200, content=manifest(key, release_fields(body)) if path.endswith('.json') else body)

    monkeypatch.setattr(app_updates.httpx, 'Client', lambda **kwargs: client(
        transport=httpx.MockTransport(respond), **kwargs,
    ))
    release = app_updates.check_release(channel)
    assert app_updates.download_release(channel, release, tmp_path).read_bytes() == body
    asset_host = 'untrusted.example'
    with pytest.raises(ValueError, match='Untrusted update redirect'):
        app_updates.check_release(channel)



def test_signed_source_commit_is_optional_but_validated():
    key = Ed25519PrivateKey.generate()
    pinned = key.public_key().public_bytes_raw()
    original = release_fields(b'MZinstaller')
    assert app_updates.Release.verify(manifest(key, original), pinned).source_sha is None
    source = 'a' * 40
    assert app_updates.Release.verify(manifest(key, dict(original, source_sha=source)), pinned).source_sha == source
    with pytest.raises(ValueError, match='Invalid release source commit'):
        app_updates.Release.verify(manifest(key, dict(original, source_sha='not-a-commit')), pinned)


def test_publisher_does_not_silently_skip_changed_source(monkeypatch):
    from scripts import publish_update
    channel = app_updates.Channel('https://updates.example', b'0' * 32)
    monkeypatch.setattr(publish_update, 'configured_channel', lambda: channel)
    monkeypatch.setattr(publish_update, 'VERSION', '2.41.20')
    monkeypatch.setattr(publish_update, 'check_release', lambda _: app_updates.Release(
        '2.41.20', 50, 'a'*64, 'published', 'b'*40,
    ))
    monkeypatch.setenv('GITHUB_SHA', 'b'*40)
    assert publish_update.should_publish() is False
    monkeypatch.setenv('GITHUB_SHA', 'c'*40)
    with pytest.raises(SystemExit, match='Increase the release version'):
        publish_update.should_publish()


def test_publisher_detects_a_stale_public_update_channel(monkeypatch):
    from scripts import publish_update
    channel = app_updates.Channel('https://updates.example', b'0' * 32)
    monkeypatch.setattr(publish_update, 'configured_channel', lambda: channel)
    monkeypatch.setattr(publish_update, 'VERSION', '2.41.20')
    monkeypatch.setattr(publish_update, 'check_release', lambda _: app_updates.Release(
        '2.41.19', 50, 'a'*64, 'previous release'))
    assert publish_update.should_publish() is True
    with pytest.raises(SystemExit, match='Public BARQ feed is stale'):
        publish_update.verify_live()
    monkeypatch.setattr(publish_update, 'check_release', lambda _: app_updates.Release(
        '2.41.20', 50, 'a'*64, 'current release'))
    publish_update.verify_live()
