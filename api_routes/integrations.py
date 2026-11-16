"""Loopback-only integration controls. The global origin/host guard is in api.py."""
from fastapi import APIRouter,HTTPException
from services.outlook_bridge import bridge

router=APIRouter(prefix='/v1/integrations',tags=['integrations'])

@router.get('/status')
def status():
    return {'outlook':bridge.status(),
            'whatsapp':{'state':'not_connected','personal_chat_access':False,
                        'note':'WhatsApp consumer chats have no supported general read API. Business Cloud API needs a business account, verified credentials and approved scopes.'}}

@router.post('/outlook/connect')
def outlook_connect():
    try:return bridge.connect()
    except RuntimeError as exc:raise HTTPException(409,str(exc))

@router.get('/outlook/inbox')
def outlook_inbox(limit:int=10):
    try:return bridge.inbox(limit)
    except (RuntimeError,ValueError) as exc:raise HTTPException(409,str(exc))
    except Exception as exc:
        # Do not echo response bodies, access tokens, or email contents in errors.
        raise HTTPException(502,'Microsoft Graph request failed: '+type(exc).__name__) from exc

@router.post('/outlook/disconnect')
def outlook_disconnect():return bridge.disconnect()
