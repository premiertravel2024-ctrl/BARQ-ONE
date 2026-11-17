"""BARQ's self-contained Windows 10/11 live wallpaper helper.

Original implementation using the pywebview/WebView2 runtime that BARQ already
bundles. Uses Explorer's desktop WorkerW host (technique also used by open-source
wallpaper engines); no Lively executable, service or extra installer required.
The UI/API process NEVER accepts arbitrary user-supplied filesystem paths:
only the native Windows file chooser adds paths to the local private manifest.
"""
from __future__ import annotations

import atexit
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from core.paths import data_dir

_MEDIA = {".mp4", ".webm", ".gif"}
_lock = threading.RLock()
_process = None


def _folder():
    path = data_dir() / "wallpapers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_path():
    return _folder() / "library.json"


def _load():
    try:
        entries = json.loads(_manifest_path().read_text(encoding="utf-8"))
        return entries if isinstance(entries, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(entries):
    path = _manifest_path()
    temp = path.with_name("library." + secrets.token_hex(6) + ".tmp")
    try:
        temp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _file(identifier):
    if not isinstance(identifier, str) or len(identifier) != 24 or not all(c in "0123456789abcdef" for c in identifier):
        raise ValueError("Invalid wallpaper ID")
    record = _load().get(identifier)
    if not isinstance(record, dict):
        raise ValueError("Wallpaper was not found in BARQ")
    path = Path(str(record.get("path", "")))
    if path.suffix.lower() not in _MEDIA or not path.is_file() or path.is_symlink():
        raise ValueError("The selected wallpaper file is unavailable")
    return path


def list_wallpapers():
    result = []
    for identifier, record in _load().items():
        try:
            source = _file(identifier)
        except (OSError, ValueError):
            continue
        result.append({"id": identifier, "title": str(record.get("title") or source.name)[:120],
                       "type": source.suffix.lower().lstrip("."), "preview_available": True})
    return result[:200]


def supported():
    return sys.platform == "win32" and sys.getwindowsversion().major >= 10


def import_file(path):
    if not supported():
        raise RuntimeError("BARQ integrated live wallpapers require Windows 10/11")
    source = Path(path)
    if source.suffix.lower() not in _MEDIA:
        raise ValueError("Choose MP4, WebM or GIF")
    if not source.is_file() or source.is_symlink() or source.stat().st_size < 1:
        raise ValueError("Wallpaper file is unavailable")
    source = source.resolve(strict=True)
    identifier = hashlib.sha256(str(source).lower().encode("utf-8")).hexdigest()[:24]
    entries = _load()
    entries[identifier] = {"path": str(source), "title": source.stem[:120]}
    _save(entries)
    return apply(identifier)


def remove_wallpaper(identifier):
    """Remove an imported entry, never the original media outside BARQ."""
    if not isinstance(identifier, str) or len(identifier) != 24 or any(c not in "0123456789abcdef" for c in identifier):
        raise ValueError("Invalid wallpaper ID")
    with _lock:
        entries = _load()
        if identifier not in entries:
            raise ValueError("Wallpaper not found in the BARQ library")
        if state().get("wallpaper_id") == identifier:
            stop()
        entries.pop(identifier)
        _save(entries)
        return {"status": "removed", "verified": True, "removed_id": identifier, "media_deleted": False}


def _state_path():
    return _folder() / "engine.json"


def _state():
    try:
        obj = json.loads(_state_path().read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def _request(state, action, volume=None):
    from urllib.error import URLError
    port, token = state.get("port"), state.get("token")
    if not isinstance(port, int) or not 1024 <= port <= 65535 or not isinstance(token, str) or len(token) < 30:
        raise RuntimeError("BARQ wallpaper player is not running")
    if action == "status":
        url = f"http://127.0.0.1:{port}/health?key={token}"
        req = Request(url)
    else:
        if action not in ("pause", "play", "volume", "stop"):
            raise ValueError("Unknown wallpaper control")
        url = f"http://127.0.0.1:{port}/control?key={token}"
        req = Request(url, method="POST", data=json.dumps({"action": action, "volume": volume}).encode(),
                      headers={"content-type": "application/json"})
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req, timeout=2) as result:
            return json.load(result)
    except (OSError, URLError, ValueError) as exc:
        raise RuntimeError("BARQ wallpaper player is not responding") from exc


def state():
    with _lock:
        if not supported():
            return {"integrated": True, "supported": False, "running": False, "backend": "webview2-workerw"}
        current = _state()
        try:
            response = _request(current, "status")
            return {"integrated": True, "supported": True, "running": response.get("ready") is True,
                    "wallpaper_id": response.get("wallpaper_id"), "backend": "webview2-workerw"}
        except RuntimeError:
            return {"integrated": True, "supported": True, "running": False, "backend": "webview2-workerw"}


def apply(identifier):
    global _process
    if not supported():
        raise RuntimeError("Native live wallpapers require Windows 10/11")
    _file(identifier)  # only allow paths previously selected through the Windows file chooser
    with _lock:
        stop()
        args = [sys.executable]
        if not getattr(sys, "frozen", False):
            args.append(str(Path(__file__).resolve().parents[1] / "desktop.py"))
        args += ["--barq-wallpaper-engine", identifier, str(os.getpid())]
        _state_path().unlink(missing_ok=True)
        try:
            with (_folder() / "engine.log").open("w", encoding="utf-8") as log:
                _process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log,
                                            stderr=log, close_fds=True,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            raise RuntimeError("Failed to start embedded BARQ wallpaper player") from exc
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and _process.poll() is None:
            current = _state()
            if current.get("pid") == _process.pid:
                try:
                    health = _request(current, "status")
                except RuntimeError:
                    health = {}
                if health.get("error"):
                    stop()
                    raise RuntimeError(health["error"])
                if health.get("ready"):
                    return {"status": "playing", "verified": True}
            time.sleep(0.1)
        code = _process.poll()
        stop()
        raise RuntimeError(f"Wallpaper engine did not initialize on this desktop (exit: {code})")


def control(action, volume=None):
    if action == "show":
        return {"status": "integrated", "verified": True}
    if action == "random":
        import random
        all_items = list_wallpapers()
        if not all_items:
            raise RuntimeError("Add a local wallpaper first")
        return apply(random.choice(all_items)["id"])
    if action == "stop":
        stop()
        return {"status": "stopped", "verified": True}
    if action not in ("pause", "play", "volume"):
        raise ValueError("Unknown wallpaper command")
    status = _request(_state(), action, volume)
    return {"status": action if status.get("ok") else "failed", "verified": bool(status.get("ok"))}


def stop():
    global _process
    with _lock:
        # A previously launched engine can outlive the transient main process handle.
        # The local authenticated control port is authoritative when its PID is valid.
        old = _state()
        if old.get("pid") != os.getpid():
            try:
                _request(old, "stop")
            except RuntimeError:
                pass
        if _process is not None:
            if _process.poll() is None:
                try:
                    _process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _process.terminate()
            _process = None
        _state_path().unlink(missing_ok=True)


atexit.register(stop)


def _embed_native_window(handle):
    """Attach only to a real Explorer WorkerW; never cover Explorer on failure."""
    import ctypes
    from ctypes import wintypes
    if sys.platform != "win32":
        raise RuntimeError("Windows required")
    user = ctypes.WinDLL("user32", use_last_error=True)
    # Explicit pointer-sized signatures are essential on Windows x64.
    user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user.SetWindowPos.restype = wintypes.BOOL
    user.GetParent.argtypes = [wintypes.HWND]
    user.GetParent.restype = wintypes.HWND
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetClientRect.restype = wintypes.BOOL
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowExW.restype = wintypes.HWND
    progman = user.FindWindowW("Progman", None)
    if not progman:
        raise RuntimeError("Windows desktop shell not found")
    result = ctypes.c_size_t()
    user.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(result))
    worker = ctypes.c_void_p()
    CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if user.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            worker.value = user.FindWindowExW(None, hwnd, "WorkerW", None)
        return True
    user.EnumWindows.argtypes = [CALLBACK, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.EnumWindows(CALLBACK(each), 0)
    if not worker.value:
        raise RuntimeError("Explorer WorkerW background was not found")
    GWL_STYLE, WS_CHILD, WS_VISIBLE, WS_POPUP = -16, 0x40000000, 0x10000000, 0x80000000
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    style = user.GetWindowLongPtrW(handle, GWL_STYLE)
    user.SetWindowLongPtrW(handle, GWL_STYLE, (style | WS_CHILD | WS_VISIBLE) & ~WS_POPUP & ~0x00C00000)
    user.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user.SetParent.restype = wintypes.HWND
    ctypes.set_last_error(0)
    previous = user.SetParent(handle, worker.value)
    if not previous and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    if user.GetParent(handle) != worker.value:
        raise RuntimeError("Explorer rejected wallpaper attachment")
    rect = wintypes.RECT()
    if not user.GetClientRect(worker.value, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not user.SetWindowPos(handle, 0, 0, 0, rect.right-rect.left, rect.bottom-rect.top,
                             0x0020 | 0x0010 | 0x0040):
        raise ctypes.WinError(ctypes.get_last_error())
    return True


def engine_main(identifier, parent_pid):
    """Separate GUI process; BARQ's main window remains responsive."""
    if not supported():
        return 2
    try:
        path = _file(identifier)
        import webview
    except (OSError, ValueError, ImportError):
        return 3
    token = secrets.token_urlsafe(32)
    ready = threading.Event()
    media_ready = threading.Event()
    gui = {"window": None, "error": ""}
    source = path
    kind = source.suffix.lower()
    asset = f"/media/{token}"
    element = (f'<img src="{asset}" alt="BARQ wallpaper">' if kind == ".gif"
               else f'<video id="wall" src="{asset}" autoplay loop muted playsinline></video>')
    document = ('<!doctype html><html><head><meta charset="utf-8"><style>'
                'html,body{width:100%;height:100%;margin:0;overflow:hidden;background:#000}'
                'video,img{width:100%;height:100%;object-fit:cover;display:block}'
                '</style></head><body>' + element +
                '<script>window.barqWallpaperControl=function(action,volume){'
                'let v=document.getElementById("wall");if(!v)return false;'
                'if(action==="pause")v.pause();if(action==="play")v.play().catch(()=>{});'
                'if(action==="volume"){v.muted=volume===0;v.volume=volume/100;}return true;'
                '};'
                f'const report=ok=>fetch("/playback?key={token}",{{method:"POST",body:JSON.stringify({{ok}})}});'
                'const media=document.querySelector("video,img");'
                'media.addEventListener(media.tagName==="IMG"?"load":"playing",()=>report(true));'
                'media.addEventListener("error",()=>report(false));'
                'if(media.tagName==="IMG"&&media.complete&&media.naturalWidth)report(true);'
                '</script></body></html>')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _headers(self, code, typ, length=None, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", typ)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if length is not None: self.send_header("Content-Length", str(length))
            for k, v in (extra or {}).items(): self.send_header(k, str(v))
            self.end_headers()

        def do_GET(self):
            parsed = urlsplit(self.path)
            key = parse_qs(parsed.query).get("key", [""])[0]
            if parsed.path == "/" and key == token:
                body = document.encode("utf-8")
                self._headers(200, "text/html; charset=utf-8", len(body)); self.wfile.write(body)
            elif parsed.path == f"/media/{token}":
                length = source.stat().st_size
                start, end = 0, length - 1
                requested = self.headers.get("Range", "")
                if requested:
                    import re
                    match = re.fullmatch(r"bytes=(\d+)-(\d*)", requested.strip())
                    if not match: self._headers(416, "text/plain"); return
                    start = int(match[1]); end = min(length-1, int(match[2]) if match[2] else length-1)
                    if start > end or start >= length: self._headers(416, "text/plain"); return
                typ = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
                headers = {"Accept-Ranges":"bytes"}
                if requested: headers["Content-Range"] = f"bytes {start}-{end}/{length}"
                self._headers(206 if requested else 200, typ, end-start+1, headers)
                try:
                    with source.open("rb") as handle:
                        handle.seek(start)
                        remaining = end-start+1
                        while remaining:
                            data = handle.read(min(262144, remaining))
                            if not data: break
                            self.wfile.write(data); remaining -= len(data)
                except (OSError, BrokenPipeError, ConnectionResetError):
                    return
            elif parsed.path == "/health" and key == token:
                body = json.dumps({"ready": ready.is_set() and media_ready.is_set(), "wallpaper_id": identifier, "error": gui["error"]}).encode()
                self._headers(200, "application/json", len(body)); self.wfile.write(body)
            else: self._headers(404, "text/plain", 0)

        def do_POST(self):
            parsed = urlsplit(self.path)
            key = parse_qs(parsed.query).get("key", [""])[0]
            if parsed.path == "/playback" and key == token:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 100: raise ValueError()
                    result = json.loads(self.rfile.read(length))
                    if result.get("ok") is True: media_ready.set()
                    else:
                        media_ready.clear()
                        gui["error"] = "Media decoder failed. Use an MP4 H.264 or supported WebM/GIF file."
                        print(gui["error"], file=sys.stderr, flush=True)
                    self._headers(204, "text/plain", 0)
                except (ValueError, OSError): self._headers(400, "text/plain", 0)
                return
            if parsed.path != "/control" or key != token: self._headers(404, "text/plain", 0); return
            if int(self.headers.get("Content-Length", "0")) > 1024: self._headers(413, "text/plain", 0); return
            try: obj = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            except (ValueError, OSError): self._headers(400, "text/plain", 0); return
            action = obj.get("action")
            if action not in ("play", "pause", "volume", "stop"): self._headers(400,"text/plain",0); return
            if action == "volume":
                amount = obj.get("volume")
                if not isinstance(amount, int) or not 0 <= amount <= 100: self._headers(400,"text/plain",0); return
            if action == "stop":
                window = gui["window"]
                if window:
                    threading.Thread(target=window.destroy, daemon=True).start()
            else:
                window = gui["window"]
                if window:
                    payload = json.dumps(action)
                    vol = int(obj.get("volume") or 0)
                    try:
                        if window.evaluate_js(f"window.barqWallpaperControl({payload},{vol})") is not True:
                            self._headers(409, "text/plain", 0); return
                    except (RuntimeError, OSError):
                        self._headers(503, "text/plain", 0); return
            body = b'{"ok":true}'
            self._headers(200, "application/json", len(body)); self.wfile.write(body)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def check_parent():
        try:
            from psutil import pid_exists
            while True:
                if not pid_exists(int(parent_pid)):
                    w = gui["window"]
                    if w: w.destroy()
                    return
                time.sleep(2)
        except (ValueError, OSError, ImportError):
            return

    loaded = threading.Event()
    published = threading.Event()
    def publish_when_ready():
        # WebView2 can fire loaded BEFORE before_show on some Windows builds.
        # Publish when both events happened, regardless of their order.
        if not ready.is_set() or not loaded.is_set() or published.is_set():
            return
        with _lock:
            if published.is_set():
                return
            record = {"pid": os.getpid(), "port": port, "token": token, "wallpaper_id": identifier}
            temp = _state_path().with_suffix(".tmp")
            temp.write_text(json.dumps(record), encoding="utf-8")
            os.replace(temp, _state_path())
            published.set()
    def attach():
        try:
            native = gui["window"].native
            handle = int(native.Handle.ToInt64())
            _embed_native_window(handle)
            ready.set()
            publish_when_ready()
        except Exception as error:
            gui["error"] = str(error)
            print("Wallpaper attachment failed:", error, file=sys.stderr, flush=True)
            threading.Thread(target=gui["window"].destroy, daemon=True).start()

    try:
        w = webview.create_window("BARQ integrated wallpaper",
            f"http://127.0.0.1:{port}/?key={token}",
            width=1280, height=720, frameless=True, easy_drag=False,
            resizable=False, on_top=False)
        gui["window"] = w
        w.events.before_show += attach
        def signal_loaded():
            loaded.set()
            publish_when_ready()
        w.events.loaded += signal_loaded
        threading.Thread(target=check_parent, daemon=True).start()
        webview.start(gui="edgechromium", debug=False)
        return 0 if ready.is_set() and loaded.is_set() and media_ready.is_set() else 4
    except (OSError, RuntimeError) as exc:
        return 5
    finally:
        httpd.shutdown(); httpd.server_close()
        current = _state()
        if current.get("pid") == os.getpid(): _state_path().unlink(missing_ok=True)

