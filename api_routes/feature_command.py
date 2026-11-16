"""One audited, consent-gated command path for the three BARQ feature modules.

Typed commands and Gemini Live tool calls must converge here instead of using
independent subprocess runners. Resource modes cannot silently suspend apps.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router=APIRouter(prefix="/v1/features",tags=["BARQ desktop features"])


class FeatureCommand(BaseModel):
    feature: str=Field(pattern="^(wallpapers|resources|watch)$")
    action: str=Field(min_length=2,max_length=30)
    wallpaper_id: str|None=None
    volume: int|None=Field(default=None,ge=0,le=100)


def run_command(feature:str,action:str,wallpaper_id:str|None=None,volume:int|None=None) -> dict:
    from computer_control.api import load_policy
    if not load_policy().enabled:
        raise PermissionError("Enable Computer Control first")
    if feature=="wallpapers":
        from api_routes.lively import wallpaper_action, Action
        if action not in ("show","play","pause","stop","random","apply","volume"):
            raise ValueError("Unsupported wallpaper action")
        result=wallpaper_action(Action(action=action,wallpaper_id=wallpaper_id,volume=volume))
        return {"status":result["status"],"verified":False,
                "message":"بعت أمر Lively، لكن لسه محتاج تتأكد إن الخلفية اتغيرت على سطح المكتب."}
    if feature=="resources":
        from services.resource_saver import snapshot,restore_all
        if action=="status":
            return {"status":"ok","result":snapshot(),
                    "message":"عرضت العمليات الحقيقية في صفحة توفير الموارد. الإيقاف محتاج موافقة صريحة."}
        if action=="restore":
            restored=restore_all()
            return {"status":"ok" if not restored["failed"] else "needs_review",
                    "result":restored,
                    "message":f"رجّعت {len(restored['restored'])} عملية موقوفة مؤقتًا. "
                              +("بعض العمليات محتاجة مراجعة." if restored["failed"] else "")}
        if action in ("gaming","focus","battery","movie"):
            return {"status":"needs_approval","mode":action,
                    "message":"جهزت وضع "+action+" للمراجعة. افتح توفير الموارد واختار البرامج غير الضرورية، وافق قبل إيقاف أي عملية."}
        raise ValueError("Unsupported resource command")
    if feature=="watch":
        from services.watch_together import create_room, close_room, status
        if action=="start":
            existing=status()
            if existing:
                return {"status":"already_exists",
                        "message":"فيه غرفة مشاهدة مفتوحة بالفعل. اقفلها من تبويب غرفة المشاهدة قبل ما تعمل غرفة جديدة."}
            details=create_room()
            # Do NOT put room passwords/URLs into a chat message: the next
            # cloud model request could include that message in its history.
            # Credentials remain retrievable only from the local Watch tab.
            return {"status":"ready_local",
                    "message":("أنشأت غرفة مشاهدة محلية. افتح تبويب غرفة المشاهدة "
                               "عشان تشوف الرابط والكود على جهازك؛ ونشر رابط خارجي محتاج موافقتك. "
                               "البث يبدأ بعد اختيار فيديو في صفحة المضيف.")}
        if action=="close":
            existing=status()
            if not existing:
                return {"status":"ok","message":"مفيش غرفة مشاهدة مفتوحة حاليًا."}
            if len(existing)>1:
                return {"status":"needs_clarification","message":"فيه أكتر من غرفة؛ اقفل الغرفة المطلوبة من تبويب المشاهدة."}
            done=close_room(existing[0]["room_id"])
            return {"status":"ok" if done else "failed",
                    "message":"قفلت غرفة المشاهدة وانتهى رابطها." if done else "تعذر قفل الغرفة."}
        if action=="status":
            return {"status":"ok","result":status(),
                    "message":f"عدد غرف المشاهدة المفتوحة: {len(status())}."}
        raise ValueError("Unknown watch command")
    raise ValueError("Unknown feature")


@router.post("/command")
def command(request:FeatureCommand):
    try:
        return run_command(request.feature,request.action,request.wallpaper_id,request.volume)
    except PermissionError as exc:
        raise HTTPException(403,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
