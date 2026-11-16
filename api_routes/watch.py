"""BARQ Watch Together controller; media remains in the selected browser File."""
from __future__ import annotations
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router=APIRouter(prefix="/v1/watchrooms",tags=["watch-together"])


def _consent():
    from computer_control.api import load_policy
    if sys.platform!="win32":
        raise HTTPException(501,"Windows desktop session required")
    if not load_policy().enabled:
        raise HTTPException(403,"Enable Computer Control in Settings first")


class Close(BaseModel):
    room_id:str=Field(min_length=10,max_length=100)

class Public(Close):
    confirmed:bool=False


@router.get("/status")
def status():
    _consent()
    from services.watch_together import status as watch_status
    return {"rooms":watch_status(),"service":"local","transcoding":False,
            "note":"One guest. Media is sent peer-to-peer if browser and NAT permit it."}


@router.get("/active")
def active():
    _consent()
    from services.watch_together import active_room
    return {"room":active_room()}


@router.post("/start")
def create():
    _consent()
    from services.watch_together import create_room
    try:
        return create_room()
    except RuntimeError as exc:
        raise HTTPException(503,str(exc)) from exc


@router.post("/close")
def close(request:Close):
    _consent()
    from services.watch_together import close_room
    return {"closed":close_room(request.room_id)}


@router.post("/publish")
def publish(request:Public):
    _consent()
    if not request.confirmed:
        raise HTTPException(403,"User must explicitly approve public tunnel")
    from services.watch_together import enable_test_tunnel
    try:
        return enable_test_tunnel(request.room_id,confirmed=True)
    except (RuntimeError,ValueError) as exc:
        raise HTTPException(503,str(exc)) from exc
