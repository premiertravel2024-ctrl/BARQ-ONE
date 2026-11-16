"""No-side-effect Windows platform and media tools detection for BARQ."""
from __future__ import annotations
import os
import shutil
import sys
from pathlib import Path


def windows_version() -> dict:
    if sys.platform!="win32":
        return {"family":"unsupported","supported":False,"release":sys.platform}
    data=sys.getwindowsversion()
    major=int(data.major);minor=int(data.minor);build=int(data.build)
    old=major==6 and minor==3
    modern=major>=10 and build>=17763
    name=("8.1" if old else
          "11" if major>=10 and build>=22000 else
          "10" if major>=10 else
          f"{major}.{minor}")
    return {"family":"legacy" if old else "modern" if modern else "unsupported",
            "supported":old or modern,"release":name,"build":build,
            "edition": "Windows 8.1" if old else "Windows 10/11" if modern else "Unsupported"}


def lively_executable() -> Path | None:
    if sys.platform!="win32":
        return None
    paths=[]
    for env in ("ProgramFiles","ProgramFiles(x86)","LOCALAPPDATA"):
        root=os.environ.get(env)
        if root:
            p=Path(root)
            paths.extend((
                p/"Lively Wallpaper"/"Lively.exe",
                p/"Programs"/"Lively Wallpaper"/"Lively.exe",
                p/"AM Lively Wallpaper"/"Lively.exe",
            ))
    candidate=shutil.which("lively.exe")
    if candidate:
        paths.insert(0,Path(candidate))
    for path in paths:
        try:
            if path.is_file() and path.name.lower()=="lively.exe":
                return path.resolve()
        except (OSError,PermissionError):
            continue
    return None


def status() -> dict:
    os_info=windows_version()
    lively=lively_executable()
    return {
        "windows":os_info,
        "lively":{"installed":lively is not None,"path":str(lively) if lively else None,
                  "version_family":"legacy" if os_info["family"]=="legacy" else "modern",
                  "license":"MS-PL" if os_info["family"]=="legacy" else "GPL-3.0",
                  "official_url":"https://github.com/rocksdanister/lively/releases"},
        "ffmpeg":{"installed":bool(shutil.which("ffmpeg")),"license":"LGPL-2.1+ / GPL-2+ depending on build"},
        "cloudflared":{"installed":bool(shutil.which("cloudflared")),"license":"Apache-2.0",
                       "note":"Quick Tunnels are for testing/development only; do not expose BARQ's private API."},
        "psutil":{"installed":_psutil_available(),"license":"BSD-3-Clause"},
        "webrtc":{"available":"browser","note":"Peer connection depends on browser and NAT; TURN relay not bundled"},
    }


def _psutil_available() -> bool:
    try:
        import psutil
        return True
    except ImportError:
        return False
