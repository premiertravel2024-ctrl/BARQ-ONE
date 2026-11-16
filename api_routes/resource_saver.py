"""Read-only preview and explicitly authorized reversible resource modes."""
from __future__ import annotations

import os
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router=APIRouter(prefix="/v1/resource-saver",tags=["resource-saver"])


def _consent():
    from computer_control.api import load_policy
    if sys.platform!="win32":
        raise HTTPException(501,"Windows desktop session required")
    if not load_policy().enabled:
        raise HTTPException(403,"Enable Computer Control in BARQ settings first")


class ApplyMode(BaseModel):
    mode: str=Field(pattern="^(gaming|focus|battery|movie)$")
    pids: list[int]=Field(default_factory=list,max_length=12)
    confirmed: bool=False
    seconds: int=Field(default=120,ge=5,le=300)


@router.get("/processes")
def process_list():
    _consent()
    from services import resource_saver
    return resource_saver.snapshot()


@router.post("/mode")
def apply_mode(request:ApplyMode):
    _consent()
    from services import resource_saver
    try:
        return resource_saver.activate(request.mode,request.pids,
                                      confirmed=request.confirmed,seconds=request.seconds)
    except PermissionError as exc:
        raise HTTPException(403,str(exc)) from exc
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(400,str(exc)) from exc


@router.post("/restore")
def restore_all():
    _consent()
    from services import resource_saver
    return resource_saver.restore_all()


@router.get("/capabilities")
def capabilities():
    """Windows edition is determined at runtime, not from a static installer guess."""
    from core.desktop_capabilities import status
    return status()
