"""Private Drive library, using the installed-app OAuth flow on loopback."""
import base64
import hashlib
import json
import re
import secrets
import time
import webbrowser
from threading import RLock
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

router = APIRouter(prefix='/drive')
SCOPE = 'https://www.googleapis.com/auth/drive.readonly'
API = 'https://www.googleapis.com/drive/v3/files'
TOKEN = 'https://oauth2.googleapis.com/token'
SERVICE = 'BARQ ONE Reading Library'
FOLDER = 'application/vnd.google-apps.folder'
MEDIA = {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}
PRIVATE = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
LOCK = RLock()
pending = None
connection = None
items = {}
failure = False


class Connect(BaseModel):
    client_id: str
    client_secret: str
    folder: str


def drive_id(value):
    return bool(re.fullmatch(r'[A-Za-z0-9_-]{10,160}', value))


def remembered():
    global connection
    if connection is None:
        try:
            import keyring
            raw = keyring.get_password(SERVICE, 'drive')
            if raw:
                connection = json.loads(raw)
        except Exception:
            pass
    return connection


@router.get('/status')
def status():
    with LOCK:
        current = remembered()
        return {'connected': bool(current), 'folder': current['folder'] if current else '',
                'failed': failure, 'pending': bool(pending and pending['expires'] > time.monotonic())}


@router.post('/connect')
def connect(config: Connect, request: Request):
    global pending, failure
    folder = config.folder.strip().rstrip('/').split('?')[0].rsplit('/', 1)[-1]
    if not drive_id(folder) or not re.fullmatch(r'[a-zA-Z0-9-]{10,100}\.apps\.googleusercontent\.com', config.client_id):
        raise HTTPException(422, 'Invalid Google desktop OAuth client ID or Drive folder')
    if not config.client_secret or len(config.client_secret) > 256:
        raise HTTPException(422, 'Invalid Google desktop OAuth client secret')
    port = request.scope.get('server', ('', 0))[1]
    if not port:
        raise HTTPException(503, 'Drive requires the local desktop server')
    redirect = f'http://127.0.0.1:{port}/v1/reading/drive/callback'
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    with LOCK:
        failure = False
        pending = {'state': state, 'verifier': verifier, 'expires': time.monotonic() + 300,
                   'client_id': config.client_id, 'client_secret': config.client_secret,
                   'folder': folder, 'redirect': redirect}
    query = urlencode({'client_id': config.client_id, 'redirect_uri': redirect,
                       'response_type': 'code', 'scope': SCOPE, 'access_type': 'offline',
                       'prompt': 'consent', 'state': state, 'code_challenge_method': 'S256',
                       'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')})
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + query
    return {'opened': webbrowser.open(url), 'url': url}


@router.get('/callback', response_class=HTMLResponse)
def callback(state: str = '', code: str = ''):
    global pending, connection, failure
    with LOCK:
        attempt = pending
        if not attempt or attempt['expires'] < time.monotonic() or not secrets.compare_digest(state.encode(), attempt['state'].encode()):
            return HTMLResponse('Invalid or expired Google connection. Return to BARQ.', 400, headers=PRIVATE)
        pending = None
        try:
            result = httpx.post(TOKEN, data={'code': code, 'grant_type': 'authorization_code',
                'client_id': attempt['client_id'], 'client_secret': attempt['client_secret'],
                'redirect_uri': attempt['redirect'], 'code_verifier': attempt['verifier']}, timeout=15)
            result.raise_for_status()
            tokens = result.json()
            if SCOPE not in tokens.get('scope', '').split() or not tokens.get('refresh_token'):
                raise ValueError('Drive authorization missing')
            connection = {key: attempt[key] for key in ('client_id', 'client_secret', 'folder')}
            connection.update(refresh_token=tokens['refresh_token'], access_token=tokens['access_token'],
                              expires=time.monotonic() + int(tokens.get('expires_in', 3600)))
            items.clear()
            try:
                import keyring
                keyring.set_password(SERVICE, 'drive', json.dumps({key: connection[key] for key in
                    ('client_id', 'client_secret', 'folder', 'refresh_token')}))
            except Exception:
                pass
        except (httpx.HTTPError, ValueError, KeyError):
            failure = True
            return HTMLResponse('Google connection failed. Return to BARQ and try again.', 400, headers=PRIVATE)
    return HTMLResponse('Google Drive connected. You can close this tab and return to BARQ ONE.', headers=PRIVATE)


@router.delete('/connection')
def disconnect():
    global connection, pending, failure
    with LOCK:
        try:
            import keyring
            if keyring.get_password(SERVICE, 'drive'):
                keyring.delete_password(SERVICE, 'drive')
        except Exception:
            if connection is None:
                raise HTTPException(503, 'Could not open credential store')
        connection = None
        pending = None
        failure = False
        items.clear()
    return {'connected': False}


def auth():
    current = remembered()
    if not current:
        raise HTTPException(401, 'Connect Google Drive first')
    if current.get('expires', 0) <= time.monotonic() + 45:
        response = httpx.post(TOKEN, data={**{key: current[key] for key in ('refresh_token', 'client_id', 'client_secret')},
            'grant_type': 'refresh_token'}, timeout=15)
        if response.status_code in (400, 401):
            raise HTTPException(401, 'Google access expired. Reconnect Google Drive.')
        response.raise_for_status()
        tokens = response.json()
        current.update(access_token=tokens['access_token'], expires=time.monotonic() + int(tokens.get('expires_in', 3600)))
    return {'Authorization': 'Bearer ' + current['access_token']}


@router.get('/catalogue')
def catalogue():
    try:
        with LOCK:
            headers = auth()
            root = connection['folder']
        upcoming = [(root, '')]
        visited = set()
        books = []
        allowed = {}
        with httpx.Client(headers=headers, timeout=15) as client:
            while upcoming:
                folder, group = upcoming.pop(0)
                if folder in visited:
                    continue
                if len(visited) >= 250 or len(books) >= 4000:
                    raise HTTPException(413, 'Drive library is too large; choose a smaller folder')
                visited.add(folder)
                page = None
                files = []
                while True:
                    params = {'q': f"'{folder}' in parents and trashed = false",
                        'fields': 'nextPageToken,files(id,name,mimeType,size)', 'pageSize': '500',
                        'supportsAllDrives': 'true', 'includeItemsFromAllDrives': 'true'}
                    if page:
                        params['pageToken'] = page
                    response = client.get(API, params=params)
                    response.raise_for_status()
                    result = response.json()
                    files.extend(item for item in result.get('files', []) if drive_id(item['id']))
                    page = result.get('nextPageToken')
                    if not page:
                        break
                pdfs = [item for item in files if item['mimeType'] == 'application/pdf'
                        and 0 < int(item.get('size', 0)) <= 64 * 1024 * 1024]
                images = {item['name'].casefold(): item for item in files if item['mimeType'] in MEDIA - {'application/pdf'}
                          and 0 < int(item.get('size', 0)) <= 8 * 1024 * 1024}
                for item in files:
                    if item['mimeType'] == FOLDER:
                        upcoming.append((item['id'], ' / '.join(filter(None, [group, item['name']]))))
                for pdf in pdfs:
                    title = re.sub(r'\.pdf$', '', pdf['name'], flags=re.I)
                    names = [title]
                    if len(pdfs) == 1:
                        names.append('cover')
                    cover = next((images[name.casefold()+ext] for name in names for ext in ('.jpg', '.jpeg', '.png', '.webp')
                                  if name.casefold()+ext in images), None)
                    allowed[pdf['id']] = pdf['mimeType']
                    if cover:
                        allowed[cover['id']] = cover['mimeType']
                    books.append({'id': pdf['id'], 'title': title, 'group': group, 'cover': cover['id'] if cover else None})
        with LOCK:
            if not connection or connection['folder'] != root:
                raise HTTPException(409, 'Drive connection changed, refresh again')
            items.clear()
            items.update(allowed)
        return {'books': books}
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, 'Could not read Google Drive. Check folder access and Drive API setup.')


@router.get('/media/{file_id}')
def media(file_id: str):
    with LOCK:
        mime = items.get(file_id)
        if not mime:
            raise HTTPException(404, 'File is outside the current Drive catalogue')
        try:
            headers = auth()
        except httpx.HTTPError:
            raise HTTPException(502, 'Could not refresh Google Drive access')
    limit = (64 if mime == 'application/pdf' else 8) * 1024 * 1024
    data = bytearray()
    try:
        with httpx.stream('GET', f'{API}/{file_id}', params={'alt': 'media', 'supportsAllDrives': 'true'},
                          headers=headers, timeout=30) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(chunk_size=65536):
                data.extend(chunk)
                if len(data) > limit:
                    raise HTTPException(413, 'Drive file is too large')
    except httpx.HTTPError:
        raise HTTPException(502, 'Could not open this file from Google Drive')
    if mime == 'application/pdf' and not data.startswith(b'%PDF-'):
        raise HTTPException(422, 'Invalid PDF')
    return Response(bytes(data), media_type=mime, headers=PRIVATE)
