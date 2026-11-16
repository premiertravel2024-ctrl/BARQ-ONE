"""Isolated, ephemeral one-host/one-guest WebRTC signaling for BARQ Watch Together.

This localhost service never serves files, the BARQ API, or directories.
The host browser alone reads the chosen video File object, then sends tracks
directly to the guest using browser WebRTC. No transcoder/relay is implied.
"""
from __future__ import annotations
import asyncio
import atexit
import json
import re
import socket
import shutil
import subprocess
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse

PORT=0  # OS-selected loopback port; never expose BARQ's admin API
app=FastAPI(title="BARQ Watch Room (isolated)",docs_url=None,redoc_url=None,openapi_url=None)
_lock=threading.RLock()
_rooms:dict[str,"Room"]={}
_server=None
_thread=None
_loop=None
_tunnel_process=None
_public_base=None


@dataclass
class Room:
    id:str
    host_token:str
    guest_token:str
    code:str
    created:float
    host:WebSocket|None=None
    guest:WebSocket|None=None
    closed:bool=False
    failed_auths:int=0
    locked_until:float=0.0


def _find(room_id:str) -> Room|None:
    with _lock:
        room=_rooms.get(room_id)
        if room and not room.closed and time.monotonic()-room.created<=7200:
            return room
        return None


def create_room() -> dict:
    _ensure_server()
    with _lock:
        if _rooms:
            raise RuntimeError("Close the existing watch room before starting another")
        room=Room(id=secrets.token_urlsafe(12),
                  host_token=secrets.token_urlsafe(32),
                  guest_token=secrets.token_urlsafe(32),
                  code=str(secrets.randbelow(900000)+100000),
                  created=time.monotonic())
        _rooms[room.id]=room
    timeout=threading.Timer(7200,close_room,args=(room.id,))
    timeout.daemon=True
    timeout.start()
    base=f"http://127.0.0.1:{PORT}/r/{room.id}"
    return {"room_id":room.id,
            "host_url":base+"?role=host&token="+room.host_token,
            "guest_url":base+"?role=guest&token="+room.guest_token,
            "room_code":room.code,
            "public":False,"status":"created",
            "note":"Guest URL is local until an explicitly approved, isolated tunnel is configured. No external access is active."}


def active_room() -> dict | None:
    """Local UI-only credentials. Never include these in Gemini tool responses."""
    with _lock:
        rooms=[room for room in _rooms.values() if not room.closed]
        if not rooms:
            return None
        room=rooms[0]
        local=f"http://127.0.0.1:{PORT}/r/{room.id}"
        remote=(_public_base if _tunnel_process is not None and _tunnel_process.poll() is None and _public_base else None)
        return {"room_id":room.id,
                "host_url":local+"?role=host&token="+room.host_token,
                "guest_url":(remote+"/r/"+room.id if remote else local)+"?role=guest&token="+room.guest_token,
                "room_code":room.code,"public":bool(remote),"status":"created"}


def enable_test_tunnel(room_id:str, *, confirmed:bool) -> dict:
    """Opt-in, temporary Cloudflare Quick Tunnel (testing only, not production).

    The tunnel exposes ONLY this isolated watch app, never BARQ's admin API.
    """
    global _tunnel_process,_public_base
    if not confirmed:
        raise PermissionError("User must approve publishing the room URL")
    room=_find(room_id)
    if room is None:
        raise ValueError("Room is closed")
    exe=shutil.which("cloudflared")
    if not exe:
        raise RuntimeError("cloudflared isn't installed; use official free binary")
    with _lock:
        if _tunnel_process and _tunnel_process.poll() is None and _public_base:
            return {"guest_url":_public_base+"/r/"+room.id+"?role=guest&token="+room.guest_token,
                    "room_code":room.code,"public":True}
    proc=subprocess.Popen(
        [exe,"tunnel","--url",f"http://127.0.0.1:{PORT}"],
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
    )
    ready=threading.Event()
    url_holder=[]
    def drain():
        if proc.stderr is None:
            ready.set();return
        for line in iter(proc.stderr.readline,b""):
            line=line.decode("utf-8",errors="replace")
            match=re.search(r"https://[a-z0-9-]{6,}\.trycloudflare\.com",line)
            if match and not url_holder:
                url_holder.append(match.group(0))
                ready.set()
        ready.set()
    threading.Thread(target=drain,daemon=True,name="BARQ-QuickTunnel-Logs").start()
    ready.wait(timeout=12)
    if not url_holder or proc.poll() is not None:
        proc.terminate()
        raise RuntimeError("Quick Tunnel wasn't established; it may be unavailable on this network")
    with _lock:
        if _tunnel_process and _tunnel_process.poll() is None:
            proc.terminate()
        else:
            _tunnel_process=proc
            _public_base=url_holder[0]
        return {"guest_url":_public_base+"/r/"+room.id+"?role=guest&token="+room.guest_token,
                "room_code":room.code,"public":True,
                "note":"Temporary Quick Tunnel for testing only. One guest, code required. Close the room to stop public access."}


def close_room(room_id:str) -> bool:
    with _lock:
        room=_rooms.pop(room_id,None)
        if not room:
            return False
        room.closed=True
    global _tunnel_process,_public_base
    if not _rooms and _tunnel_process and _tunnel_process.poll() is None:
        _tunnel_process.terminate()
        _tunnel_process=None
        _public_base=None
    if _loop:
        for ws in (room.guest,room.host):
            if ws:
                try:
                    asyncio.run_coroutine_threadsafe(ws.close(code=1001),_loop)
                except RuntimeError:
                    pass
    return True


def close_all():
    with _lock:
        ids=list(_rooms)
    for room_id in ids:
        close_room(room_id)
    if _server:
        _server.should_exit=True
    global _tunnel_process,_public_base
    if _tunnel_process and _tunnel_process.poll() is None:
        _tunnel_process.terminate()
    _tunnel_process=None
    _public_base=None


def status() -> list[dict]:
    with _lock:
        return [{"room_id":r.id,"guest_connected":r.guest is not None,
                 "host_connected":r.host is not None,
                 "age_seconds":int(time.monotonic()-r.created)}
                for r in _rooms.values() if not r.closed]


def _ensure_server():
    global _thread,_server,_loop,PORT
    if _thread and _thread.is_alive() and _server and _server.started:
        return
    import uvicorn
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1",0))
        sock.listen(64)
    except OSError:
        sock.close()
        raise RuntimeError("Could not reserve an isolated watch-room loopback port")
    PORT=sock.getsockname()[1]
    done=threading.Event()
    failure=[]
    def serve():
        global _loop,_server
        try:
            _loop=asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
            config=uvicorn.Config(app,host="127.0.0.1",port=PORT,access_log=False,
                                  log_level="error",lifespan="off")
            _server=uvicorn.Server(config)
            done.set()
            _loop.run_until_complete(_server.serve(sockets=[sock]))
        except Exception as exc:
            failure.append(str(exc)[:130])
            done.set()
        finally:
            try:
                sock.close()
                _loop.close()
            except Exception:
                pass
    _thread=threading.Thread(target=serve,daemon=True,name="BARQ-Watch-Signaling")
    _thread.start()
    done.wait(timeout=2)
    for _ in range(45):
        if failure:
            raise RuntimeError("Could not start local watch server")
        if _server and _server.started:
            return
        time.sleep(.05)
    raise RuntimeError("Watch server did not become ready")


@app.get("/r/{room_id}")
def room_page(room_id:str,role:str="",token:str=""):
    room=_find(room_id)
    if not room or role not in ("host","guest"):
        return JSONResponse({"error":"Room unavailable"},status_code=404)
    right=room.host_token if role=="host" else room.guest_token
    if not token or not secrets.compare_digest(token,right):
        return JSONResponse({"error":"Invalid room token"},status_code=403)
    from services.watch_web import PAGE
    return HTMLResponse(PAGE,headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer",
                                     "Content-Security-Policy":("default-src 'self'; img-src 'self' data: blob:; "
                                       "media-src blob:; connect-src 'self' ws: wss:; "
                                       "style-src 'unsafe-inline'; script-src 'unsafe-inline'")})


@app.websocket("/signal/{room_id}")
async def signal(ws:WebSocket,room_id:str):
    room=_find(room_id)
    role=ws.query_params.get("role","")
    token=ws.query_params.get("token","")
    code=ws.query_params.get("code","")
    if not room or role not in ("host","guest"):
        await ws.close(code=1008);return
    expected=room.host_token if role=="host" else room.guest_token
    if not secrets.compare_digest(token,expected):
        await ws.close(code=1008);return
    if role=="guest":
        with _lock:
            now=time.monotonic()
            if now<room.locked_until:
                allowed=False
            else:
                if now>=room.locked_until and room.failed_auths>=6:
                    room.failed_auths=0
                allowed=secrets.compare_digest(code,room.code)
                if allowed:
                    room.failed_auths=0
                else:
                    room.failed_auths+=1
                    if room.failed_auths>=6:
                        room.locked_until=now+300.0
        if not allowed:
            await ws.close(code=1008)
            return
    with _lock:
        if room.closed or (room.host if role=="host" else room.guest) is not None:
            await ws.close(code=1008);return
        if role=="host": room.host=ws
        else: room.guest=ws
    await ws.accept()
    last=0.;count=0
    try:
        await ws.send_json({"type":"ready","role":role})
        other=room.guest if role=="host" else room.host
        if other:
            await other.send_json({"type":"peer-joined","role":role})
            await ws.send_json({"type":"peer-joined","role":"guest" if role=="host" else "host"})
        allowed_host={"offer","ice","chat","typing","reaction","sync","settings","subtitle"}
        allowed_guest={"answer","ice","chat","typing","reaction","request-pause","request-seek"}
        while not room.closed:
            text=await ws.receive_text()
            if len(text)>65536:
                await ws.close(code=1009);break
            now=time.monotonic()
            if now-last>1:count=0;last=now
            count+=1
            if count>30:
                await ws.close(code=1008);break
            try:
                payload=json.loads(text)
            except ValueError:
                continue
            if not isinstance(payload,dict):
                continue
            kind=payload.get("type")
            if kind not in (allowed_host if role=="host" else allowed_guest):
                continue
            if kind in ("chat","reaction","typing"):
                content=str(payload.get("text") or "")[:500]
                payload={"type":kind,"text":content,"role":role}
            elif kind=="subtitle":
                cue=payload.get("value")
                if not isinstance(cue,str):
                    continue
                payload={"type":"subtitle","value":cue[:400]}
            else:
                payload={"type":kind,"value":payload.get("value")}
            other=room.guest if role=="host" else room.host
            if other:
                await other.send_json(payload)
    except Exception:
        pass
    finally:
        with _lock:
            if role=="host" and room.host is ws:
                room.host=None
            elif role=="guest" and room.guest is ws:
                room.guest=None
        other=room.guest if role=="host" else room.host
        if other and not room.closed:
            try:await other.send_json({"type":"peer-left","role":role})
            except Exception:pass
        if role=="host":
            close_room(room_id)


atexit.register(close_all)
