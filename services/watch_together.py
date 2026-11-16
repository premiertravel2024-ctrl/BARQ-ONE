"""Isolated, ephemeral one-host/one-guest WebRTC signaling for BARQ Watch Together.

This localhost service never serves files, the BARQ API, or directories.
The host browser reads the chosen media, then sends audio and video tracks
directly to the guest using browser WebRTC. No transcoder/relay is implied.
"""
from __future__ import annotations
import asyncio
import atexit
import json
import ipaddress
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
import re
import socket
import shutil
import subprocess
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from dataclasses import dataclass

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

PORT=0  # OS-selected loopback port; never expose BARQ's admin API
app=FastAPI(title="BARQ Watch Room (isolated)",docs_url=None,redoc_url=None,openapi_url=None)
_lock=threading.RLock()
_startup_lock=threading.Lock()
_tunnel_setup_lock=threading.Lock()
_lan_binding: tuple[str, int] | None = None
_rooms:dict[str,"Room"]={}
_guest_invites: dict[str,tuple[str,str,float]] = {}
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
    mode:str="video"
    lan:bool=False
    timer:threading.Timer|None=None
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


def _private_ipv4(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    return any(address in network for network in (
        ipaddress.IPv4Network("192.168.0.0/16"), ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"), ipaddress.IPv4Network("100.64.0.0/10"),
    ))


def _lan_address() -> str:
    # UDP connect selects the local route. No packet is sent.
    candidates=[]
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1",9))
            address=probe.getsockname()[0]
            if _private_ipv4(address):
                candidates.append(address)
        except OSError:
            pass
    try:
        addresses=socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        addresses=[]
    try:
        import psutil
        candidates.extend(entry.address for entries in psutil.net_if_addrs().values()
                          for entry in entries if entry.family==socket.AF_INET)
    except (ImportError,OSError):
        pass
    for address in dict.fromkeys([*candidates,*addresses]):
        if not _private_ipv4(address):
            continue
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as check:
            try:
                check.bind((address,0))
            except OSError:
                continue
            return address
    raise RuntimeError("مفيش عنوان شبكة محلية متاح. اتصل بنفس الشبكة أو استخدم الدعوة المؤقتة عبر الإنترنت.")


def _room_details(room: Room) -> dict:
    local=f"http://127.0.0.1:{PORT}/r/{room.id}"
    remote=(_public_base if _tunnel_process is not None and _tunnel_process.poll() is None and _public_base else None)
    nearby=f"http://{_lan_binding[0]}:{_lan_binding[1]}/r/{room.id}" if room.lan and _lan_binding else None
    return {"room_id":room.id,"mode":room.mode,
            "host_url":local+"?role=host&token="+room.host_token+"&mode="+room.mode,
            "guest_url":(remote+"/r/"+room.id if remote else nearby or local)+"?role=guest&token="+room.guest_token+"&mode="+room.mode,
            "room_code":room.code,"lan":room.lan,"public":bool(remote),"status":"created",
            "host_connected":room.host is not None,"guest_connected":room.guest is not None}


def create_room(*,mode: str="video",lan: bool=False) -> dict:
    if mode not in ("video","music"):
        raise ValueError("Unsupported room mode")
    with _startup_lock:
        with _lock:
            if _rooms:
                raise RuntimeError("Close the existing room before starting another")
        if lan:
            _ensure_server(_lan_address())
        else:
            _ensure_server()
        with _lock:
            room=Room(id=secrets.token_urlsafe(12),
                      host_token=secrets.token_urlsafe(32),
                      guest_token=secrets.token_urlsafe(32),
                      code=str(secrets.randbelow(900000)+100000),
                      created=time.monotonic(),mode=mode,lan=lan)
            room.timer=threading.Timer(7200,close_room,args=(room.id,))
            room.timer.daemon=True
            _rooms[room.id]=room
            room.timer.start()
            return _room_details(room)


def active_room() -> dict | None:
    """Local UI-only credentials. Never include these in Gemini tool responses."""
    with _lock:
        room=next((room for room in _rooms.values() if not room.closed),None)
        return _room_details(room) if room else None


_CLOUDFLARED_VERSION="2026.11.0"
_CLOUDFLARED_SHA256="d5c1d82031da6253dcdcff64c944cd0fe063016edeb2e4fd088075fc9bd52d0a"


def _tunnel_binary() -> str:
    if sys.platform!="win32":
        executable=shutil.which("cloudflared")
        if executable:
            return executable
        raise RuntimeError("cloudflared is unavailable on this system")

    from core.paths import data_dir
    folder=data_dir()/"tools"/"cloudflared"/_CLOUDFLARED_VERSION
    executable=folder/"cloudflared.exe"

    def verified(path: Path) -> bool:
        try:
            with path.open("rb") as body:
                return hashlib.file_digest(body,"sha256").hexdigest()==_CLOUDFLARED_SHA256
        except OSError:
            return False

    with _tunnel_setup_lock:
        if verified(executable):
            return str(executable)
        temporary=None
        try:
            folder.mkdir(parents=True,exist_ok=True)
            url=("https://github.com/cloudflare/cloudflared/releases/download/"
                 +_CLOUDFLARED_VERSION+"/cloudflared-windows-amd64.exe")
            with tempfile.NamedTemporaryFile(dir=folder,suffix=".download",delete=False) as out:
                temporary=Path(out.name)
                deadline=time.monotonic()+75
                count=0
                with urlopen(url,timeout=12) as source:
                    while chunk:=source.read(256*1024):
                        count+=len(chunk)
                        if count>80*1024*1024 or time.monotonic()>deadline:
                            raise RuntimeError("Cloudflare download exceeded its limit")
                        out.write(chunk)
            if not verified(temporary):
                raise RuntimeError("Cloudflare checksum verification failed")
            os.replace(temporary,executable)
            return str(executable)
        except (OSError,URLError,RuntimeError) as exc:
            raise RuntimeError("تعذّر تجهيز رابط الإنترنت. اتأكد من الاتصال وجرب تاني.") from exc
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


def _reachable_guest_page(base: str,room: Room,process) -> bool:
    url=base+"/r/"+room.id+"?role=guest&token="+room.guest_token+"&mode="+room.mode
    deadline=time.monotonic()+20
    while time.monotonic()<deadline and process.poll() is None and not room.closed:
        try:
            with urlopen(url,timeout=4) as response:
                if response.status==200:
                    return True
        except (OSError,URLError):
            time.sleep(1)
    return False


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
    with _lock:
        if _tunnel_process and _tunnel_process.poll() is None and _public_base:
            return _room_details(room)
    exe=_tunnel_binary()
    if _find(room_id) is not room:
        raise RuntimeError("Room closed while setting up the internet invite")
    proc=subprocess.Popen(
        [exe,"tunnel","--no-autoupdate","--url",f"http://127.0.0.1:{PORT}"],
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
    ready.wait(timeout=25)
    if not url_holder or not _reachable_guest_page(url_holder[0],room,proc):
        if proc.poll() is None:
            proc.terminate()
        raise RuntimeError("تعذّر فتح رابط الغرفة من الإنترنت. جرّب تاني أو استخدم نفس الشبكة.")
    with _lock:
        if _tunnel_process and _tunnel_process.poll() is None:
            proc.terminate()
        else:
            _tunnel_process=proc
            _public_base=url_holder[0]
        if _rooms.get(room.id) is not room or room.closed:
            if _tunnel_process is proc:
                proc.terminate()
                _tunnel_process=None
                _public_base=None
            raise RuntimeError("Room closed while opening the tunnel")
        return _room_details(room)


def close_room(room_id:str) -> bool:
    with _lock:
        room=_rooms.pop(room_id,None)
        if not room:
            return False
        room.closed=True
        if room.timer:
            room.timer.cancel()
    global _tunnel_process,_public_base
    with _lock:
        if not _rooms:
            if _tunnel_process and _tunnel_process.poll() is None:
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
        _guest_invites.clear()
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


def _ensure_server(lan_ip: str | None=None):
    global _thread,_server,_loop,PORT,_lan_binding
    if _thread and _thread.is_alive():
        current_address = _lan_binding[0] if _lan_binding else None
        if _server and _server.started and current_address==lan_ip:
            return
        if _server:
            _server.should_exit=True
        _thread.join(timeout=4)
        if _thread.is_alive():
            raise RuntimeError("The previous room is still shutting down. Retry shortly.")
    import uvicorn
    addresses = ["127.0.0.1",lan_ip] if lan_ip else ["127.0.0.1"]
    sockets=[]
    _lan_binding=None
    try:
        for address in addresses:
            sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sockets.append(sock)
            sock.bind((address,0))
            sock.listen(64)
    except OSError as exc:
        for sock in sockets:
            sock.close()
        raise RuntimeError("Could not reserve the room ports. Check the local network.") from exc
    PORT=sockets[0].getsockname()[1]
    if lan_ip:
        _lan_binding=(lan_ip,sockets[1].getsockname()[1])
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
            _loop.run_until_complete(_server.serve(sockets=sockets))
        except Exception as exc:
            failure.append(str(exc)[:130])
            done.set()
        finally:
            try:
                for sock in sockets:
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
def room_page(request: Request,room_id:str,role:str="",token:str=""):
    room=_find(room_id)
    if not room or role not in ("host","guest"):
        return JSONResponse({"error":"Room unavailable"},status_code=404)
    if role=="host" and not _local_host(request):
        return JSONResponse({"error":"Host page is local only"},status_code=403)
    right=room.host_token if role=="host" else room.guest_token
    if not token or not secrets.compare_digest(token.encode(),right.encode()):
        return JSONResponse({"error":"Invalid room token"},status_code=403)
    from services.watch_web import PAGE
    return HTMLResponse(PAGE,headers=_page_headers())


def _page_headers():
    return {"Cache-Control":"no-store","Referrer-Policy":"no-referrer",
            "Content-Security-Policy":("default-src 'self'; img-src 'self' data: blob:; "
              "media-src blob: https:; connect-src 'self' ws: wss:; "
              "style-src 'unsafe-inline'; script-src 'unsafe-inline'")}


def join_invite(guest_url: str, code: str) -> str:
    try:
        url=urlsplit(guest_url)
        port=url.port
    except ValueError as exc:
        raise ValueError("كود دعوة الغرفة غير صالح") from exc
    authority=url.hostname or ""
    local_network=url.scheme=="http" and _private_ipv4(authority) and port is not None and port>=1024
    internet=(url.scheme=="https" and port in (None,443)
              and re.fullmatch(r"[a-z0-9-]+[.]trycloudflare[.]com",authority))
    params=parse_qs(url.query)
    token=params.get("token",[""])[0]
    mode=params.get("mode",["video"])[0]
    name=re.fullmatch(r"/r/([A-Za-z0-9_-]{16})",url.path)
    if (not (local_network or internet) or url.username or url.password or url.fragment
            or not name or params.get("role")!=["guest"]
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}",token)
            or not re.fullmatch(r"[0-9]{6}",code) or mode not in ("video","music")):
        raise ValueError("كود دعوة الغرفة غير صالح")
    scheme="ws" if local_network else "wss"
    query=urlencode({"role":"guest","token":token,"code":code})
    signal_url=urlunsplit((scheme,url.netloc,"/signal/"+name[1],query,""))
    with _startup_lock:
        if not (_thread and _thread.is_alive() and _server and _server.started):
            _ensure_server()
        with _lock:
            key=secrets.token_urlsafe(24)
            _guest_invites.clear()
            _guest_invites[key]=(signal_url,mode,time.monotonic()+7200)
    return f"http://127.0.0.1:{PORT}/guest/{key}?role=guest&mode={mode}&paired=1"


def _guest_invitation(key: str):
    with _lock:
        invite=_guest_invites.get(key)
        return invite if invite and invite[2]>time.monotonic() else None


@app.get("/guest/{key}")
def local_guest_page(request: Request,key: str):
    if not _local_host(request) or not _guest_invitation(key):
        return JSONResponse({"error":"Invalid local invitation"},status_code=404)
    from services.watch_web import PAGE
    return HTMLResponse(PAGE,headers=_page_headers())


@app.websocket("/join-signal/{key}")
async def join_signal(ws: WebSocket,key: str):
    from websockets.asyncio.client import connect
    from websockets.exceptions import WebSocketException

    class DirectConnection(connect):
        def process_redirect(self, exc):
            # The validated invite must remain the sole outbound destination.
            return exc

    invite=_guest_invitation(key)
    if not invite or not _local_host(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        async with DirectConnection(invite[0],open_timeout=8,close_timeout=2,max_size=65536,proxy=None) as remote:
            async def upstream():
                while True:
                    message=await ws.receive_text()
                    if len(message)>65536:
                        return
                    await remote.send(message)

            async def downstream():
                async for message in remote:
                    if isinstance(message,str):
                        await ws.send_text(message)

            tasks={asyncio.create_task(upstream()),asyncio.create_task(downstream())}
            try:
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    except (OSError,TimeoutError,RuntimeError,WebSocketException,WebSocketDisconnect):
        pass
    finally:
        try:
            await ws.close()
        except (RuntimeError,WebSocketDisconnect):
            pass


def _local_host(connection) -> bool:
    host=connection.headers.get("host","").split(":",1)[0]
    peer=connection.client.host if connection.client else ""
    return host in ("127.0.0.1","localhost","testserver") and peer in ("127.0.0.1","::1","testclient")


@app.websocket("/signal/{room_id}")
async def signal(ws:WebSocket,room_id:str):
    room=_find(room_id)
    role=ws.query_params.get("role","")
    token=ws.query_params.get("token","")
    code=ws.query_params.get("code","")
    if not room or role not in ("host","guest"):
        await ws.close(code=1008);return
    expected=room.host_token if role=="host" else room.guest_token
    if (role=="host" and not _local_host(ws)) or not secrets.compare_digest(token.encode(),expected.encode()):
        await ws.close(code=1008);return
    if role=="guest":
        with _lock:
            now=time.monotonic()
            if now<room.locked_until:
                allowed=False
            else:
                if now>=room.locked_until and room.failed_auths>=6:
                    room.failed_auths=0
                allowed=secrets.compare_digest(code.encode(),room.code.encode())
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
        occupied=room.closed or (room.host if role=="host" else room.guest) is not None
        if not occupied:
            if role=="host": room.host=ws
            else: room.guest=ws
    if occupied:
        await ws.close(code=1008)
        return
    last=0.;count=0
    try:
        await ws.accept()
        await ws.send_json({"type":"ready","role":role})
        other=room.guest if role=="host" else room.host
        if other:
            guest=ws if role=="guest" else other
            host_header=guest.headers.get("host","").split(":",1)[0]
            connection="lan" if _private_ipv4(host_header) else "internet"
            await other.send_json({"type":"peer-joined","role":role,"connection":connection})
            await ws.send_json({"type":"peer-joined","role":"guest" if role=="host" else "host","connection":connection})
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


atexit.register(close_all)
