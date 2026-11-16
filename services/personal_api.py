from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field
from services import personal_assistant as personal
import asyncio
router=APIRouter(prefix='/v1/personal',tags=['personal-assistant'])
API_LOOP=None
class Command(BaseModel):text:str=Field(min_length=1,max_length=500)
class Settings(BaseModel):
 owner_name:str=Field(min_length=1,max_length=60)
 routines:dict[str,list[str]]
 favorites:dict[str,str]
 notify_voice:bool=False

@router.get('/settings')
def settings():
 data=personal.read()
 from voice.owner_voice import available,enrolled
 from services.assistant_runtime import hotkey_status
 return {**data,'hotkey':hotkey_status,'owner_model_ready':available(),'owner_voice_enrolled':enrolled()}

@router.put('/settings')
def update(body:Settings,request:Request):
 from voice.wake import _same_origin
 _same_origin(request)
 try:return personal.configure(**body.model_dump())
 except ValueError as exc:raise HTTPException(400,str(exc))

@router.post('/command')
async def command(body:Command,request:Request):
 global API_LOOP
 API_LOOP=asyncio.get_running_loop()
 from voice.wake import _same_origin
 _same_origin(request)
 return await personal.execute(body.text)

@router.get('/notifications')
def notifications():return {'items':[n for n in personal.read()['notifications'] if not n.get('read')]}

class Ack(BaseModel):ids:list[str]=Field(max_length=100)
@router.post('/notifications/ack')
def ack(body:Ack,request:Request):
 from voice.wake import _same_origin
 _same_origin(request)
 with personal._lock:
  data=personal.read()
  for note in data['notifications']:
   if note['id'] in body.ids:note['read']=True
  personal.write(data)
 return {'ok':True}

@router.delete('/watches/{watch_id}')
def delete_watch(watch_id:str,request:Request):
 from voice.wake import _same_origin
 _same_origin(request)
 with personal._lock:
  data=personal.read();data['watches']=[w for w in data['watches'] if w['id']!=watch_id];personal.write(data)
 return {'ok':True}

async def bind_loop():
 global API_LOOP
 API_LOOP=asyncio.get_running_loop()
