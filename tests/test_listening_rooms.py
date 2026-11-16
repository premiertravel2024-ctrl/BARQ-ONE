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


def test_room_socket_accepts_desktop_port_and_checks_origin():
    app = FastAPI()
    app.include_router(router)
    origin = 'http://127.0.0.1:53821'
    with TestClient(app, base_url=origin) as client:
        created = client.post('/v1/listening/rooms').json()
        code = created['code']
        socket_url = f'ws://127.0.0.1:53821/v1/listening/rooms/{code}/ws?secret={created["secret"]}'
        try:
            with pytest.raises(WebSocketDisconnect) as error:
                with client.websocket_connect(socket_url, headers={'Origin': 'http://127.0.0.1:8000'}):
                    pass
            assert error.value.code == 1008

            with client.websocket_connect(socket_url, headers={'Origin': origin}) as host:
                assert host.receive_json()['participants'] == 1
                with client.websocket_connect(socket_url, headers={'Origin': origin}) as guest:
                    assert host.receive_json()['participants'] == 2
                    assert guest.receive_json()['participants'] == 2
                    host.send_json({'type': 'chat', 'text': 'أهلاً'})
                    assert guest.receive_json()['text'] == 'أهلاً'
        finally:
            _rooms.pop(code, None)
