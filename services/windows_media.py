"""Windows media transport uses GSMTC, scoped to an actual playback session."""
import asyncio,sys
async def control(action):
 if sys.platform!='win32':raise ValueError('التحكم في الميديا متاح على Windows فقط.')
 try:
  from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Sessions
 except ImportError:raise ValueError('مكتبة Windows Media غير موجودة داخل النسخة.')
 manager=await Sessions.request_async();session=manager.get_current_session()
 if session is None:raise ValueError('مفيش مشغّل ميديا نشط بيدعم تحكم Windows.')
 method={'play':'try_play_async','pause':'try_pause_async','next':'try_skip_next_async','previous':'try_skip_previous_async'}.get(action)
 if not method:raise ValueError('أمر ميديا غير صالح')
 success=await asyncio.wait_for(getattr(session,method)(),timeout=3)
 if not success:raise ValueError('المشغّل لم يؤكد تنفيذ أمر الميديا.')
 return 'المشغّل أكد أمر الميديا: '+action+'.'

def selected_text(clipboard=False):
 if sys.platform!='win32':raise ValueError('قراءة المحدد متاحة على Windows فقط.')
 if clipboard:
  import pyperclip
  return str(pyperclip.paste())[:5000]
 from pywinauto import Desktop
 active=Desktop(backend='uia').get_active()
 for control in [active]+active.descendants()[:150]:
  try:
   if not control.has_keyboard_focus() or bool(getattr(control.element_info,'is_password',False)):continue
   selection=control.iface_text.GetSelection()
   if selection.Length:return selection.GetElement(0).GetText(5000)
  except Exception:continue
 return ''
