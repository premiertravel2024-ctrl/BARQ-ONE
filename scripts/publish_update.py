"""Prepare the public trust settings and sign an installer already verified by CI."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.app_updates import Channel, Release, check_release, installer_name, usable_origin, version_key
from core.version import VERSION


def configured_channel() -> Channel | None:
    origin = os.environ.get('BARQ_UPDATE_ORIGIN', '').strip()
    key = os.environ.get('BARQ_UPDATE_PUBLIC_KEY', '').strip()
    if not origin and not key:
        return None
    key_bytes = base64.b64decode(key, validate=True)
    Ed25519PublicKey.from_public_bytes(key_bytes)
    return Channel(usable_origin(origin), key_bytes)


def configure() -> None:
    channel = configured_channel()
    if channel is None:
        if os.environ.get('GITHUB_REF_TYPE') == 'tag':
            raise SystemExit('Set BARQ_UPDATE_ORIGIN and BARQ_UPDATE_PUBLIC_KEY before publishing release tags')
        return
    Path('assets/update-channel.json').write_text(json.dumps({
        'origin': channel.origin,
        'public_key': base64.b64encode(channel.public_key).decode('ascii')
    }), encoding='utf-8')


def sign(artifact: Path, tag: str) -> None:
    channel = configured_channel()
    if channel is None or tag != 'v' + VERSION:
        raise SystemExit('The release tag must match the built BARQ version and an update channel must be configured')
    setup = artifact / installer_name(VERSION)
    evidence = json.loads((artifact / 'release-evidence.json').read_text(encoding='utf-8-sig'))
    with setup.open('rb') as file:
        digest = hashlib.file_digest(file, 'sha256').hexdigest()
    if evidence['sha256']['release/' + setup.name] != digest:
        raise SystemExit('Setup does not match Windows CI evidence')
    notes = os.environ.get('BARQ_UPDATE_NOTES', '').strip()[:1500]
    data = json.dumps({
        'schema': 1, 'product': 'BARQ ONE', 'platform': 'windows-x64', 'version': VERSION,
        'size': setup.stat().st_size, 'sha256': digest, 'notes': notes,
    }, ensure_ascii=False).encode()
    private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(os.environ['BARQ_UPDATE_PRIVATE_KEY'], validate=True))
    manifest = json.dumps({
        'payload': base64.b64encode(data).decode('ascii'),
        'signature': base64.b64encode(private.sign(data)).decode('ascii'),
    }).encode()
    Release.verify(manifest, channel.public_key)
    try:
        previous = check_release(channel)
    except httpx.HTTPStatusError as error:
        if error.response.status_code != 404:
            raise
    else:
        if version_key(previous.version) > version_key(VERSION) or previous.version == VERSION and previous.digest != digest:
            raise SystemExit('The public channel already advertises a newer release or different installer for this version')
    (artifact / 'latest.json').write_bytes(manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('configure', 'sign'))
    parser.add_argument('--artifact', type=Path, default=Path('verified-windows'))
    parser.add_argument('--tag', default='')
    args = parser.parse_args()
    if args.command == 'configure':
        configure()
    else:
        sign(args.artifact, args.tag)
