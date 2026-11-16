"""Focused room protocol tests (no cloud model or desktop hardware needed)."""
import asyncio
import pytest
from fastapi import HTTPException
from api_routes.listening_rooms import _lookup, _rooms, create_room, join_room, Join, _snapshot


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
