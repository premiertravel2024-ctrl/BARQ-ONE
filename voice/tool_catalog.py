"""Visible BARQ voice assistant tool catalogue, no side effects or network probes."""
from __future__ import annotations
import os
import sys

def catalogue() -> dict:
    from voice.gemini import gemini_key
    from computer_control.api import load_policy
    from voice.wake import wake_preferences, wake_status
    local_only=os.getenv('LOCAL_ONLY','false').strip().lower() in ('1','true','yes')
    google=bool(gemini_key()) and not local_only
    windows=sys.platform=='win32'
    try:desktop=windows and bool(load_policy().enabled)
    except (OSError,ValueError,TypeError,AttributeError):desktop=False
    try:background=bool(wake_preferences().get('enabled'))
    except (OSError,ValueError,TypeError):background=False
    available={
      'web_search':('بحث الإنترنت','public','internet',google),
      'city_weather':('الطقس وتوقعات 3 أيام','public','internet',google),
      'public_github':('بحث GitHub ومعلومات المستودعات','public','internet',google),
      'packages':('إصدارات PyPI وnpm','public','internet',google),
      'local_clock':('الوقت والتاريخ من الكمبيوتر','utility','offline',google),
      'calculator':('حاسبة محلية','utility','offline',google),
      'unit_convert':('تحويل الوحدات','utility','offline',google),
      'windows_apps':('فتح التطبيقات والتحكم في النوافذ','computer','windows',google and desktop),
      'gaming_companion':('نصائح شاشة اللعبة وقياس FPS عند الطلب','computer','windows',google and desktop),
      'youtube_playback':('اختيار فيديو أو أغنية وفتحها على YouTube','computer','windows',google and desktop),
      'screen_reader':('قراءة عناصر ونص النافذة الحالية محليًا','computer','windows',google and desktop),
      'device_files':('بحث الملفات والمشاريع المحلية','computer','windows',google and desktop),
      'device_sensors':('معلومات الجهاز وحساسات الحرارة','computer','windows',google and windows),
      'github_setup':('استيراد مستودع للمشروع بموافقة آمنة','computer','windows',google and desktop),
    }
    return {'google_voice_configured':google,'windows_control_enabled':desktop,
            'background_listener_enabled':background,'tools':[
      {'id':key,'label':label,'group':group,'requires':required,
       'ready_in_google_voice':ready,'note':'أداة معلومات فقط، بدون صلاحية على ملفاتك' if group in ('public','utility') else 'تخضع لصلاحيات Windows وأذونات المشروع'}
      for key,(label,group,required,ready) in available.items()]}
