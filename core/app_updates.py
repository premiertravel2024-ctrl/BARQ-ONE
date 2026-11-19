"""Discover and install signed BARQ desktop releases."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin, urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.paths import data_dir, resource
from core.version import VERSION

MAX_FEED = 32 * 1024
MAX_INSTALLER = 1024 * 1024 * 1024


def version_key(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}', value):
        raise ValueError('Invalid release version')
    return tuple(int(part) for part in value.split('.'))


def installer_name(version: str) -> str:
    version_key(version)
    return f'BARQ_Setup_{version}.exe'


def usable_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.hostname == 'github.com':
        valid_path = re.fullmatch(r'/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+/?', parsed.path)
        if not valid_path or parsed.path.rstrip('/').rsplit('/', 1)[-1] in ('.', '..'):
            raise ValueError('Invalid GitHub update repository')
    elif parsed.path not in ('', '/'):
        raise ValueError('Invalid update server')
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError('Invalid update server')
    return value.rstrip('/')


@dataclass(frozen=True)
class Channel:
    origin: str
    public_key: bytes

    @classmethod
    def load(cls) -> Channel | None:
        try:
            obj = json.loads(resource('assets', 'update-channel.json').read_text(encoding='utf-8-sig'))
            return cls(usable_origin(obj['origin']), base64.b64decode(obj['public_key'], validate=True))
        except (OSError, TypeError, KeyError, ValueError):
            return None


@dataclass(frozen=True)
class Release:
    version: str
    size: int
    digest: str
    notes: str

    @property
    def path(self) -> str:
        return f'/releases/{self.version}/{installer_name(self.version)}'

    @classmethod
    def verify(cls, raw: bytes, pinned_key: bytes) -> Release:
        envelope = json.loads(raw)
        signed = base64.b64decode(envelope['payload'], validate=True)
        signature = base64.b64decode(envelope['signature'], validate=True)
        Ed25519PublicKey.from_public_bytes(pinned_key).verify(signature, signed)
        data = json.loads(signed)
        version_key(data['version'])
        if (data['schema'] != 1 or data['product'] != 'BARQ ONE' or data['platform'] != 'windows-x64'
                or type(data['size']) is not int or not 0 < data['size'] <= MAX_INSTALLER
                or not re.fullmatch(r'[0-9a-f]{64}', data['sha256'])
                or not isinstance(data['notes'], str) or len(data['notes']) > 1500):
            raise ValueError('Invalid signed release')
        return cls(data['version'], data['size'], data['sha256'], data['notes'])


@contextmanager
def update_response(client: httpx.Client, channel: Channel, path: str):
    github = urlsplit(channel.origin).hostname == 'github.com'
    if not github:
        with client.stream('GET', channel.origin + path) as response:
            yield response
        return

    prefix = urlsplit(channel.origin).path + '/releases/download/'
    if path == '/latest.json':
        url = channel.origin + '/releases/latest/download/latest.json'
        filename = 'latest.json'
    else:
        _, _, version, filename = path.split('/')
        url = channel.origin + f'/releases/download/v{version}/{filename}'

    for _ in range(4):
        with client.stream('GET', url) as response:
            if not response.is_redirect:
                yield response
                return
            target = urljoin(url, response.headers.get('location', ''))
            parsed = urlsplit(target)
            valid_release = parsed.hostname == 'github.com' and re.fullmatch(
                re.escape(prefix) + r'v[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}/' + re.escape(filename),
                parsed.path,
            )
            valid_asset = parsed.hostname in {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
            if (parsed.scheme != 'https' or parsed.port not in (None, 443) or parsed.username
                    or parsed.password or parsed.fragment or not (valid_release or valid_asset)):
                raise ValueError('Untrusted update redirect')
            url = target
    raise ValueError('Too many update redirects')


def check_release(channel: Channel) -> Release:
    with httpx.Client(timeout=12, follow_redirects=False) as client:
        with update_response(client, channel, '/latest.json') as response:
            response.raise_for_status()
            chunks = bytearray()
            for chunk in response.iter_bytes(chunk_size=4096):
                chunks.extend(chunk)
                if len(chunks) > MAX_FEED:
                    raise ValueError('Unexpected update response length')
    return Release.verify(bytes(chunks), channel.public_key)


def download_release(channel: Channel, release: Release, directory: Path, progress=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / installer_name(release.version)
    if target.is_file() and target.stat().st_size == release.size:
        with target.open('rb') as cached:
            if hashlib.file_digest(cached, 'sha256').hexdigest() == release.digest:
                return target

    for attempt in range(1, 4):
        temporary = None
        try:
            with NamedTemporaryFile(dir=directory, prefix='barq-', suffix='.part', delete=False) as output:
                temporary = Path(output.name)
                count = 0
                digest = hashlib.sha256()
                if progress:
                    progress(count, release.size, attempt)
                with httpx.Client(timeout=httpx.Timeout(45, connect=12), follow_redirects=False) as client:
                    with update_response(client, channel, release.path) as response:
                        response.raise_for_status()
                        for chunk in response.iter_bytes(chunk_size=256 * 1024):
                            count += len(chunk)
                            if count > release.size:
                                raise ValueError('Unexpected installer size')
                            digest.update(chunk)
                            output.write(chunk)
                            if progress:
                                progress(count, release.size, attempt)
                if count != release.size:
                    raise httpx.ReadError('Installer download ended before the expected size')
                if digest.hexdigest() != release.digest:
                    raise ValueError('Installer failed verification')
            temporary.replace(target)
            return target
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            retryable = not isinstance(error, httpx.HTTPStatusError) or error.response.status_code in (
                404, 408, 429, 500, 502, 503, 504)
            if attempt == 3 or not retryable:
                raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        time.sleep(attempt)
    raise RuntimeError('Update retries exhausted')


@dataclass(frozen=True)
class PendingInstall:
    path: Path
    release: Release
    install_directory: Path

    def launch(self) -> None:
        with self.path.open('rb') as verified:
            if hashlib.file_digest(verified, 'sha256').hexdigest() != self.release.digest:
                raise ValueError('Installer changed after verification')
        subprocess.Popen([
            str(self.path), '/SILENT', '/NORESTART', '/CLOSEAPPLICATIONS', '/BARQUPDATE=1',
            '/DIR=' + str(self.install_directory),
        ], cwd=self.install_directory)


class UpdateBridge:
    """Only expose version-based actions, with a pinned feed and the local WebView origin."""

    def __init__(self, url: str):
        self._url = url
        self._window = None
        self._lock = threading.Lock()
        self._channel = Channel.load()
        self._directory = Path(sys.executable).resolve().parent
        self._supported = (sys.platform == 'win32' and getattr(sys, 'frozen', False)
                           and (self._directory / 'unins000.exe').is_file())
        self._pending: PendingInstall | None = None
        self._download_progress = None

    def _trusted(self) -> bool:
        if self._window is None:
            return False
        current = urlsplit(self._window.get_current_url() or '')
        return current.path == '/' and current.netloc == urlsplit(self._url).netloc and current.scheme == 'http'

    def check_update(self) -> dict:
        result = {'current': VERSION, 'status': 'unconfigured'}
        if not self._trusted() or not self._supported:
            return {'current': VERSION, 'status': 'unavailable'}
        if self._channel is not None:
            try:
                release = check_release(self._channel)
                if version_key(release.version) > version_key(VERSION):
                    return dict(result, status='available', version=release.version, notes=release.notes, size=release.size)
                return dict(result, status='current')
            except Exception:
                logging.getLogger(__name__).exception('BARQ update check failed')
                return dict(result, status='error')
        return result

    def update_progress(self) -> dict:
        if not self._trusted():
            return {}
        return self._download_progress or {}

    def _report_progress(self, count: int, total: int, attempt: int) -> None:
        self._download_progress = {'received': count, 'total': total, 'attempt': attempt}

    def cancel_staged_update(self) -> dict:
        if not self._trusted() or not self._supported:
            return {'status': 'unavailable'}
        with self._lock:
            self._pending = None
        return {'status': 'cancelled'}

    def download_update(self, version: str, stage_only: bool = False) -> dict:
        if not self._trusted() or not self._supported or self._channel is None:
            return {'status': 'unavailable'}
        if not self._lock.acquire(blocking=False):
            return {'status': 'busy'}
        try:
            if self._pending is None or self._pending.release.version != version:
                release = check_release(self._channel)
                if release.version != version or version_key(release.version) <= version_key(VERSION):
                    return {'status': 'changed'}
                path = download_release(self._channel, release, data_dir() / 'updates', self._report_progress)
                self._pending = PendingInstall(path, release, self._directory)
            if stage_only:
                return {'status': 'staged'}
            from voice.background_window import shutdown
            def close_for_install():
                shutdown()
                self._window.destroy()
            timer = threading.Timer(.5, close_for_install)
            timer.daemon = True
            timer.start()
            return {'status': 'installing'}
        except httpx.HTTPError:
            logging.getLogger(__name__).exception('BARQ update transfer failed')
            return {'status': 'network-error'}
        except ValueError:
            logging.getLogger(__name__).exception('BARQ update integrity check failed')
            return {'status': 'verification-error'}
        except Exception:
            logging.getLogger(__name__).exception('BARQ could not download the update')
            return {'status': 'error'}
        finally:
            self._download_progress = None
            self._lock.release()
