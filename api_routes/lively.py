"""BARQ built-in desktop wallpaper controller; legacy Lively CLI retained only as fallback."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import shutil
import threading
import sys

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.desktop_capabilities import lively_executable, windows_version

router=APIRouter(prefix="/v1/wallpapers",tags=["wallpapers"])
_install_lock=threading.Lock()
_install_job=None


def _consent():
    from computer_control.api import load_policy
    if sys.platform!="win32":
        raise HTTPException(501,"Windows only")
    if not load_policy().enabled:
        raise HTTPException(403,"Enable Computer Control first")


def _native_enabled():
    return sys.platform == "win32" and windows_version()["family"] == "modern" and os.environ.get("BARQ_WALLPAPER_LEGACY") != "1"


def _native_command(args):
    from services import native_wallpaper as native
    if args[:2] == ["setwp", "--file"] and len(args) == 3:
        return native.control("random") if args[2] == "random" else (
            native.apply(args[2]) if len(args[2]) == 24 and args[2].isalnum() else native.import_file(args[2]))
    if args[:2] == ["closewp", "--monitor"] and len(args) == 3:
        return native.control("stop")
    if args[:2] == ["app", "--play"] and len(args) == 3:
        return native.control("play" if args[2] == "true" else "pause")
    if args[:2] == ["app", "--volume"] and len(args) == 3:
        return native.control("volume", int(args[2]))
    if args == ["app", "--showApp", "true"]:
        return native.control("show")
    raise HTTPException(400, "Unsupported wallpaper action")


def _library_folder() -> Path | None:
    root=os.environ.get("LOCALAPPDATA")
    if not root:
        return None
    candidates=(
        Path(root)/"Lively Wallpaper"/"Library"/"wallpapers",
        Path(root)/"Lively Wallpaper"/"Library"/"wallpaper",
        Path(root)/"Packages"/"12030rocksdanister.LivelyWallpaper_97hta09mmv6hy"/"LocalCache"/"Local"/"Lively Wallpaper"/"Library"/"wallpapers",
    )
    return next((path for path in candidates if path.is_dir()),None)


def items() -> list[dict]:
    if _native_enabled():
        from services.native_wallpaper import list_wallpapers
        return list_wallpapers()
    root=_library_folder()
    if not root:
        return []
    entries=[]
    for folder in sorted(root.iterdir(),key=lambda p:p.name.lower())[:200]:
        try:
            if not folder.is_dir() or folder.is_symlink():
                continue
            path=folder/"LivelyInfo.json"
            if not path.is_file() or path.stat().st_size>32768:
                continue
            data=json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data,dict):
                continue
            title=str(data.get("Title") or folder.name)[:100]
            preview=None
            for name in ("thumbnail.jpg","thumbnail.png","preview.jpg"):
                target=folder/name
                if target.is_file() and not target.is_symlink():
                    preview=name
                    break
            entries.append({"id":folder.name,"title":title,
                            "type":str(data.get("Type") or "wallpaper"),
                            "preview_available":bool(preview)})
        except (OSError,ValueError,PermissionError):
            continue
    return entries


def _wallpaper(id: str) -> Path:
    if not id or len(id)>100 or "/" in id or "\\" in id or id in (".",".."):
        raise HTTPException(400,"Invalid wallpaper id")
    root=_library_folder()
    if not root:
        raise HTTPException(404,"Lively library not found")
    target=root/id
    if target.is_symlink() or not (target/"LivelyInfo.json").is_file():
        raise HTTPException(404,"Wallpaper is not in installed Lively library")
    try:
        if not target.resolve().is_relative_to(root.resolve()):
            raise HTTPException(403,"Wallpaper outside allowed library")
    except OSError:
        raise HTTPException(404,"Wallpaper missing")
    return target


def _run(args: list[str]) -> dict:
    _consent()
    if _native_enabled():
        try:
            return _native_command(args)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (RuntimeError, OSError) as exc:
            raise HTTPException(503, str(exc)) from exc
    exe=lively_executable()
    if not exe:
        raise HTTPException(404,"Lively Wallpaper not installed. Download only from the official release.")
    if not windows_version()["supported"]:
        raise HTTPException(501,"Windows version unsupported")
    try:
        res=subprocess.run([str(exe),*args],capture_output=True,text=True,timeout=9,
                           creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    except (OSError,subprocess.TimeoutExpired):
        raise HTTPException(503,"Lively command timed out or could not start")
    if res.returncode:
        raise HTTPException(502,"Lively rejected command")
    # A successful CLI exit only confirms command delivery, not wallpaper
    # playback. Do not claim a visually verified wallpaper.
    return {"status":"command_sent","verified":False}


def _installer_status() -> str:
    with _install_lock:
        if _install_job is None:
            return "idle"
        code=_install_job.poll()
        return "running" if code is None else "finished" if code==0 else "failed"


@router.post("/install")
def install():
    _consent()
    if _native_enabled():
        return {"status":"integrated", "verified":True}
    if lively_executable():
        return {"status":"installed"}
    if windows_version()["family"]!="modern":
        raise HTTPException(501,"The supported Lively installer requires Windows 10 or 11")
    winget=shutil.which("winget.exe")
    if not winget:
        raise HTTPException(503,"Windows App Installer (winget) is unavailable")
    global _install_job
    with _install_lock:
        if _install_job and _install_job.poll() is None:
            return {"status":"running"}
        try:
            _install_job=subprocess.Popen(
                [winget,"install","--id","rocksdanister.LivelyWallpaper","--exact","--source","winget","--interactive"],
                creationflags=getattr(subprocess,"CREATE_NEW_CONSOLE",0),
            )
        except OSError as exc:
            raise HTTPException(503,"Could not launch the Windows installer") from exc
    return {"status":"running"}


class Action(BaseModel):
    action: str=Field(pattern="^(play|pause|stop|show|volume|apply|random)$")
    wallpaper_id: str|None=None
    volume: int|None=Field(default=None,ge=0,le=100)


@router.get("/status")
def wallpaper_status(metrics: bool=True):
    from core.desktop_capabilities import status
    try:
        import psutil
    except ImportError:
        psutil=None
    data=status()
    if _native_enabled():
        from services import native_wallpaper as native
        return {"capabilities":data["windows"],"lively":data["lively"],
                "engine":native.state(),"library":native.list_wallpapers(),
                "features":{"remove_wallpaper":True,"native_engine_handshake":2},
                "processes":[],"installer":"finished","can_install":False,
                "autopause":"Embedded BARQ engine; no separate Lively installation"}
    processes=[]
    try:
        for process in (psutil.process_iter(["pid","name","memory_info","cpu_times"]) if metrics and psutil else []):
            name=str(process.info.get("name") or "").lower()
            if name in ("lively.exe","livelywpf.exe","livelycefstream.exe","livelympv.exe","livelyvlc.exe"):
                mem=process.info.get("memory_info")
                processes.append({"pid":process.pid,"name":name,
                                  "ram_mb":round(mem.rss/1048576,1) if mem else None,
                                  "cpu_percent":None})
    except (OSError,PermissionError):
        pass
    return {"capabilities":data["windows"],"lively":data["lively"],
            "library":items(),"processes":processes,"installer":_installer_status(),
            "can_install":data["windows"]["family"]=="modern" and bool(shutil.which("winget.exe")),
            "autopause":"Configure fullscreen and battery rules in Lively Settings"}


@router.get("/preview/{wallpaper_id}")
def wallpaper_preview(wallpaper_id:str):
    # Preview is read-only for an already user-picked media ID and requires no
    # computer-control permission.  Import/apply/delete still require consent.
    # A disabled control policy must not cause blank gallery thumbnails.
    if _native_enabled():
        from services.native_wallpaper import _file
        try:
            return FileResponse(_file(wallpaper_id))
        except (ValueError, OSError) as exc:
            raise HTTPException(404, "Wallpaper preview unavailable") from exc
    _consent()
    folder=_wallpaper(wallpaper_id)
    for name in ("thumbnail.jpg","thumbnail.png","preview.jpg"):
        target=folder/name
        if target.is_file() and not target.is_symlink():
            return FileResponse(target,media_type="image/png" if name.endswith(".png") else "image/jpeg")
    raise HTTPException(404,"Preview unavailable")


@router.post("/pick-local")
def pick_local_wallpaper():
    """Import ONLY a media file selected through the native Windows picker.

    A model, API client or browser cannot provide an arbitrary filesystem path.
    File content is never uploaded, copied or sent to a cloud service.
    """
    _consent()
    try:
        from tkinter import Tk, filedialog
        root=Tk()
        root.withdraw()
        root.attributes("-topmost",True)
        try:
            chosen=filedialog.askopenfilename(
                parent=root,title="BARQ — اختر خلفية فيديو أو GIF",
                filetypes=[
                    ("Video and animated images","*.mp4 *.webm *.gif"),
                    ("Video","*.mp4 *.webm"),
                    ("GIF","*.gif"),
                ])
        finally:
            root.destroy()
    except (ImportError, OSError,RuntimeError) as exc:
        raise HTTPException(503,"Windows file picker unavailable") from exc
    if not chosen:
        return {"status":"cancelled","verified":False}
    path=Path(chosen)
    if path.suffix.lower() not in {".mp4",".webm",".gif"}:
        raise HTTPException(400,"Unsupported media type")
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size<=0:
            raise HTTPException(400,"Selected media file is not accessible")
    except (OSError,PermissionError) as exc:
        raise HTTPException(400,"Selected media file cannot be read") from exc
    # Official Lively CLI imports media files from outside the library.
    return _run(["setwp","--file",str(path)])


@router.delete("/{wallpaper_id}")
def remove_wallpaper(wallpaper_id: str):
    """Remove the BARQ library record only; never erase the user's own media."""
    _consent()
    if not _native_enabled():
        raise HTTPException(501, "Removing legacy Lively library entries is not supported by BARQ")
    from services import native_wallpaper as native
    try:
        return native.remove_wallpaper(wallpaper_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/action")
def wallpaper_action(request:Action):
    if request.action=="show":
        return _run(["app","--showApp","true"])
    if request.action in ("play","pause"):
        return _run(["app","--play","true" if request.action=="play" else "false"])
    if request.action=="stop":
        return _run(["closewp","--monitor","-1"])
    if request.action=="volume":
        if request.volume is None:
            raise HTTPException(400,"Volume required")
        return _run(["app","--volume",str(request.volume)])
    if request.action=="random":
        if windows_version()["family"]=="legacy":
            raise HTTPException(501,"Random CLI was introduced after the legacy Lively release")
        return _run(["setwp","--file","random"])
    if request.action=="apply":
        if not request.wallpaper_id:
            raise HTTPException(400,"Choose a wallpaper")
        if _native_enabled():
            _consent()
            from services import native_wallpaper as native
            try:
                return native.apply(request.wallpaper_id)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except (RuntimeError, OSError) as exc:
                raise HTTPException(503, str(exc)) from exc
        return _run(["setwp","--file",str(_wallpaper(request.wallpaper_id))])
    raise HTTPException(400,"Unknown action")

