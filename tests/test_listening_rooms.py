"""Focused room protocol tests (no cloud model or desktop hardware needed)."""
import asyncio
import pytest
from fastapi import FastAPI, HTTPException, WebSocketDisconnect
from fastapi.testclient import TestClient
from api_routes.listening_rooms import _lookup, _rooms, create_room, join_room, Join, _snapshot, router


def test_room_creation_invite_validation():
    created = asyncio.run(create_room())
    assert len(created['code']) == 8
    room = _lookup(created['code'], created['secret'])
    assert _snapshot(room)['participants'] == 0
    assert asyncio.run(join_room(Join(**created)))['capacity'] == 2
    with pytest.raises(HTTPException) as exc:
        _lookup(created['code'], created['secret'] + 'wrong')
    assert exc.value.status_code == 404
    _rooms.pop(created['code'])


def test_desktop_room_connects_on_its_dynamic_port_and_checks_origin():
    app = FastAPI()
    app.include_router(router)
    origin = 'http://127.0.0.1:49152'
    with TestClient(app, base_url=origin) as client:
        response = client.post('/v1/listening/rooms')
        assert response.status_code == 200
        room = response.json()
        socket_url = f"ws://127.0.0.1:49152/v1/listening/rooms/{room['code']}/ws?secret={room['secret']}"
        try:
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(socket_url, headers={'origin': 'http://127.0.0.1:49153'}):
                    pytest.fail('a different local origin was accepted')
            assert exc.value.code == 1008
            with client.websocket_connect(socket_url, headers={'origin': origin}) as host:
                assert host.receive_json()['participants'] == 1
                with client.websocket_connect(socket_url, headers={'origin': origin}) as guest:
                    assert host.receive_json()['participants'] == 2
                    assert guest.receive_json()['participants'] == 2
                    host.send_json({'type': 'playback', 'track': 'https://example.com/music.mp3', 'position': 12})
                    assert guest.receive_json()['position'] == 12
        finally:
            _rooms.pop(room['code'], None)
