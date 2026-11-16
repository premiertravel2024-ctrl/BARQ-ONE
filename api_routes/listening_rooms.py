"""Private, ephemeral two-person listening rooms.

Synchronizes playback metadata and chat; never proxies or redistributes media.
The underlying BARQ desktop API remains loopback-only by design.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

router = APIRouter(prefix='/v1/listening', tags=['listening'])
MAX_ROOMS = 32
ROOM_TTL = 6 * 3600


@dataclass
class Room:
    code: str
    secret: str
    created: float = field(default_factory=time.monotonic)
    sockets: dict[str, WebSocket] = field(default_factory=dict)
    track: str = ''
    title: str = ''
    paused: bool = True
    position: float = 0.0
    updated: float = field(default_factory=time.time)


_rooms: dict[str, Room] = {}


class Join(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    secret: str = Field(min_length=20, max_length=128)


def _prune():
    now = time.monotonic()
    for code, room in list(_rooms.items()):
        if not room.sockets and now - room.created > ROOM_TTL:
            _rooms.pop(code, None)


def _lookup(code: str, secret: str) -> Room:
    room = _rooms.get(code.upper())
    if not room or not secrets.compare_digest(room.secret, secret):
        raise HTTPException(404, 'الغرفة غير موجودة أو رابط الدعوة غير صحيح')
    return room


@router.post('/rooms')
async def create_room():
    _prune()
    if len(_rooms) >= MAX_ROOMS:
        raise HTTPException(429, 'عدد الغرف وصل للحد المؤقت')
    code = secrets.token_hex(4).upper()
    secret = secrets.token_urlsafe(24)
    _rooms[code] = Room(code, secret)
    return {'code': code, 'secret': secret, 'capacity': 2}


@router.post('/rooms/join')
async def join_room(data: Join):
    room = _lookup(data.code, data.secret)
    if len(room.sockets) >= 2:
        raise HTTPException(409, 'الغرفة ممتلئة (شخصين فقط)')
    return {'code': room.code, 'capacity': 2}


def _snapshot(room: Room):
    return {'type': 'state', 'code': room.code, 'participants': len(room.sockets),
            'track': room.track, 'title': room.title, 'paused': room.paused,
            'position': room.position, 'updated': room.updated}


async def _broadcast(room: Room, message: dict):
    for ws in list(room.sockets.values()):
        try:
            await ws.send_json(message)
        except (RuntimeError, OSError, WebSocketDisconnect):
            pass


@router.websocket('/rooms/{code}/ws')
async def room_socket(ws: WebSocket, code: str):
    # WebSocket requests bypass HTTP middleware: validate the same local-only
    # boundary explicitly. Never accept arbitrary browser origins.
    host = ws.headers.get('host', '').lower()
    origin = ws.headers.get('origin', '')
    peer = ws.client.host if ws.client else ''
    try:
        hostname = urlsplit(f'//{host}').hostname
    except ValueError:
        hostname = None
    if hostname not in ('127.0.0.1', 'localhost', '::1', 'testserver') or peer not in ('127.0.0.1', '::1', 'testclient'):
        await ws.close(code=1008)
        return
    if origin:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            await ws.close(code=1008)
            return
        expected_scheme = 'https' if ws.url.scheme == 'wss' else 'http'
        if parsed.scheme != expected_scheme or parsed.netloc.lower() != host:
            await ws.close(code=1008)
            return
    try:
        room = _lookup(code, ws.query_params.get('secret', ''))
    except HTTPException:
        await ws.close(code=1008)
        return
    if len(room.sockets) >= 2:
        await ws.close(code=1008)
        return
    client_id = secrets.token_hex(8)
    room.sockets[client_id] = ws
    try:
        await ws.accept()
        await _broadcast(room, _snapshot(room))
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue
            kind = msg.get('type')
            if kind == 'chat':
                content = str(msg.get('text', '')).strip()[:500]
                if content:
                    await _broadcast(room, {'type': 'chat', 'id': secrets.token_hex(6),
                                            'text': content, 'sender': client_id, 'at': time.time()})
            elif kind == 'playback':
                url = str(msg.get('track', ''))[:2048]
                parts = urlsplit(url)
                # Only direct HTTPS media URLs, never local file paths or script protocols.
                if url and (parts.scheme != 'https' or not parts.netloc or parts.username or parts.password):
                    await ws.send_json({'type': 'error', 'message': 'استخدم رابط HTTPS مباشر للصوت'})
                    continue
                room.track = url
                room.title = str(msg.get('title', ''))[:120]
                room.paused = bool(msg.get('paused', True))
                try:
                    room.position = max(0.0, min(float(msg.get('position', 0)), 86400.0))
                except (ValueError, TypeError):
                    room.position = 0.0
                room.updated = time.time()
                await _broadcast(room, _snapshot(room))
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        room.sockets.pop(client_id, None)
        if room.sockets:
            await _broadcast(room, _snapshot(room))
