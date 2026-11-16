"""Desktop emergency stop, local notifications, and native global stop shortcut."""
import asyncio,sys,threading

generation=0
hotkey_status={'ready':False,'shortcut':'Ctrl+Alt+Pause'}
def emergency_stop():
 global generation
 generation+=1
 from services import personal_assistant as personal
 with personal._lock:
  data=personal.read();data['paused']=True;data['gaming_monitor']=False;personal.write(data)
 if sys.platform=='win32':
  import winsound
  try:winsound.PlaySound(None,0)
  except RuntimeError:pass
 from build.jobs import JOBS
 for job in list(JOBS.values()):
  task=job.get('task')
  if task and not task.done():task.cancel()
 from voice.wake import set_wake_enabled_from_tray,stop_listener
 set_wake_enabled_from_tray(False);stop_listener()
 try:
  from computer_control import api
  if api._manager:api._manager.stop()
 except Exception:pass
 try:
  from voice.background_window import stop_output
  stop_output()
 except Exception:pass
 return {'status':'stopped','message':'وقفت الاستماع والصوت ومهمة التحكم الحالية. الاستئناف من أيقونة برق.'}

def native_hotkey(stop):
 if sys.platform!='win32':return
 import ctypes,time
 from ctypes import wintypes
 user=ctypes.windll.user32
 # Ctrl+Alt+Pause. Registration never hooks or records other keys.
 if not user.RegisterHotKey(None,0xBA01,0x4000|0x0002|0x0001,0x13):
  hotkey_status['error']='الاختصار محجوز؛ استخدم إيقاف فوري من أيقونة برق'
  return
 hotkey_status['ready']=True
 message=wintypes.MSG()
 try:
  while not stop.wait(.06):
   while user.PeekMessageW(ctypes.byref(message),None,0,0,1):
    if message.message==0x0312:request_stop()
 finally:user.UnregisterHotKey(None,0xBA01)


def request_stop():
 from services.personal_api import API_LOOP
 if API_LOOP and API_LOOP.is_running():API_LOOP.call_soon_threadsafe(emergency_stop)
 else:
  from voice.background_window import stop_output
  stop_output()


_speech_lock=threading.Lock()
def speak_notification(message):
 if sys.platform!='win32' or not _speech_lock.acquire(blocking=False):return
 try:
  import time
  from voice import wake,live
  from services.personal_assistant import read
  if live.ACTIVE_LIVE_CALLS or read().get('paused'):return
  from voice.local_speaker import synthesize_sapi
  marker=generation
  wav=synthesize_sapi(message,arabic_only=True)
  if marker!=generation or live.ACTIVE_LIVE_CALLS:return
  import winsound
  wake._wake_handoff_until=time.monotonic()+25
  wake.stop_listener()
  wake._speaking_until=time.monotonic()+25
  try:
   if marker==generation:winsound.PlaySound(wav,winsound.SND_MEMORY|winsound.SND_SYNC|winsound.SND_NODEFAULT)
  finally:
   wake._speaking_until=0;wake._wake_handoff_until=0
   if wake.wake_preferences()['enabled'] and not live.ACTIVE_LIVE_CALLS:wake.start_listener()
 except (OSError,RuntimeError,ValueError):pass
 finally:_speech_lock.release()
