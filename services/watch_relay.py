"""Hosted BARQ signaling and short-lived TURN credentials (no file endpoints)."""
import base64
import hmac
import os
import re
import secrets
import time

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket
from pydantic import BaseModel
from typing import Literal

from services import watch_together as watch

app = FastAPI(title="BARQ Room Relay", docs_url=None, redoc_url=None, openapi_url=None)


def _turn_config():
    urls = [value.strip() for value in os.environ.get("BARQ_TURN_URLS", "").split(",") if value.strip()]
    secret = os.environ.get("BARQ_TURN_SECRET", "")
    if not urls or len(secret) < 32 or any(not re.fullmatch(r"turns?:[A-Za-z0-9.-]+:[0-9]{1,5}(?:\?transport=(?:udp|tcp))?", url) for url in urls):
        raise HTTPException(503, "TURN service is not configured")
    return urls, secret


@app.get("/health")
def health():
    _turn_config()
    if len(os.environ.get("BARQ_RELAY_CREATE_TOKEN", "")) < 32:
        raise HTTPException(503, "Room creation is not configured")
    return {"status": "ok"}


class Start(BaseModel):
    mode: Literal["video", "music"] = "video"


@app.post("/api/rooms", status_code=201)
def create(data: Start, authorization: str = Header(default="")):
    key = os.environ.get("BARQ_RELAY_CREATE_TOKEN", "")
    if len(key) < 32 or not hmac.compare_digest(authorization.encode(), ("Bearer " + key).encode()):
        raise HTTPException(401, "Invalid relay token")
    _turn_config()
    with watch._lock:
        if len(watch._rooms) >= 64:
            raise HTTPException(503, "Room capacity reached")
        room = watch.Room(secrets.token_urlsafe(12), secrets.token_urlsafe(32),
                          secrets.token_urlsafe(32), str(secrets.randbelow(900000) + 100000),
                          time.monotonic(), mode=data.mode)
        watch._register_room(room)
    return {"room_id": room.id, "host_token": room.host_token,
            "guest_token": room.guest_token, "code": room.code}


@app.delete("/api/rooms/{room_id}")
def close(room_id: str, authorization: str = Header(default="")):
    room = watch._find(room_id)
    if room and not hmac.compare_digest(authorization.encode(), ("Bearer " + room.host_token).encode()):
        raise HTTPException(403, "Invalid room owner")
    if room:
        watch.close_room(room_id)
    return {"closed": True}


@app.get("/r/{room_id}")
def player(request: Request, room_id: str, role: str = "", token: str = ""):
    if role != "guest":
        raise HTTPException(404, "Guest page only")
    return watch.room_page(request, room_id, role, token)


@app.websocket("/signal/{room_id}")
async def socket(ws: WebSocket, room_id: str):
    try:
        urls, secret = _turn_config()
    except HTTPException:
        await ws.close(code=1013)
        return
    username = f"{int(time.time()) + 7500}:{room_id}"
    credential = base64.b64encode(hmac.digest(secret.encode(), username.encode(), "sha1")).decode()
    await watch.signal_session(ws, room_id, hosted=True, ice_servers=[
        {"urls": urls, "username": username, "credential": credential}
    ])
