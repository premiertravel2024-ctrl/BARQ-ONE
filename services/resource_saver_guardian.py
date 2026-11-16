"""Detached BARQ Resource Saver crash-recovery guardian.

Spawned only after a foreground user explicitly confirms a vetted pause.
The guardian has the same Windows user rights, cannot elevate, cannot stop or
launch apps, cannot modify startup services, and ONLY calls psutil.resume()
for matching PID/create_time records written by BARQ itself.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _read_state(path:Path)->dict:
    try:
        document=json.loads(path.read_text(encoding="utf-8"))
        if isinstance(document,dict) and isinstance(document.get("paused"),dict):
            return document
    except (OSError,ValueError,TypeError):
        pass
    return {"paused":{}}


def restore(path:Path)->dict:
    try:
        import psutil
    except ImportError:
        return {"resumed":[],"failed":["psutil_missing"]}
    doc=_read_state(path)
    successful=[]
    failed=[]
    keep={}
    for key,record in doc["paused"].items():
        try:
            pid=int(key)
            start=float(record["start"])
            proc=psutil.Process(pid)
            if abs(proc.create_time()-start)>.1:
                # PID was reused; never resume the wrong process.
                continue
            proc.resume()
            successful.append(pid)
        except (psutil.NoSuchProcess,psutil.ZombieProcess):
            continue
        except (psutil.AccessDenied,OSError,ValueError,TypeError,KeyError):
            failed.append(key)
            keep[key]=record
    doc["paused"]=keep
    try:
        tmp=path.with_name(path.name+".guardian.tmp")
        tmp.write_text(json.dumps(doc),encoding="utf-8")
        os.replace(tmp,path)
    except OSError:
        pass
    return {"resumed":successful,"failed":failed}


def guard(parent_pid:int,parent_started:float,path:Path)->int:
    """Monitor both parent identity and wall-clock expiry; never trust PID alone."""
    try:
        import psutil
    except ImportError:
        return 2
    for _ in range(900):
        doc=_read_state(path)
        if not doc["paused"]:
            return 0
        expires=float(doc.get("expires_at") or 0)
        if expires and time.time()>=expires:
            break
        try:
            p=psutil.Process(parent_pid)
            if abs(p.create_time()-parent_started)>.1 or not p.is_running():
                break
        except (psutil.NoSuchProcess,psutil.ZombieProcess):
            break
        except psutil.AccessDenied:
            # Don't assume parent died just because Windows denies access.
            if expires and time.time()>=expires:
                break
        time.sleep(.35)
    result=restore(path)
    return 1 if result["failed"] else 0


def main(argv:list[str]|None=None)->int:
    args=list(sys.argv[1:] if argv is None else argv)
    if len(args)!=3:
        return 2
    try:
        pid=int(args[0]);start=float(args[1]);path=Path(args[2]).resolve()
        from core.paths import data_dir
        # No arbitrary path supplied from a model or network:
        # only BARQ's configured data directory is a valid journal root.
        if path.parent!=data_dir() or path.name!="resource_saver_paused.json":
            return 2
        if pid<1 or start<=0:
            return 2
    except (OSError,ValueError,TypeError):
        return 2
    return guard(pid,start,path)


if __name__=="__main__":
    raise SystemExit(main())
