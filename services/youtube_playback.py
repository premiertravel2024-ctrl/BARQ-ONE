"""Best-effort native YouTube Play button, only in the verified foreground browser.

No hotkeys, profile access, injected JavaScript or blind coordinates. Never moves
focus back to a browser after the user switches away. A short deadline prevents
late clicks from a slow accessibility call.
"""
import sys,time
PLAY={'play (k)','تشغيل (k)','تشغيل الفيديو','play video'}
PAUSE={'pause (k)','إيقاف مؤقت (k)','ايقاف مؤقت (k)','pause video'}

def _browser_window():
    import ctypes,psutil
    from ctypes import wintypes
    from pywinauto import Desktop
    user=ctypes.windll.user32;user.GetForegroundWindow.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    hwnd=user.GetForegroundWindow();pid=wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if psutil.Process(pid.value).name().lower() not in {'chrome.exe','msedge.exe','firefox.exe','brave.exe','opera.exe'}:return None
    window=Desktop(backend='uia').window(handle=hwnd)
    return window,lambda:user.GetForegroundWindow()==hwnd

def verify_playback(title:str,*,policy,window_probe=None,budget:float=2.5)->bool:
    if sys.platform!='win32' and window_probe is None:return False
    from computer_control.safety.policy import Decision
    deadline=time.monotonic()+budget;clicked=False;bound_handle=None
    for _ in range(5):
        if time.monotonic()>=deadline:return False
        try:
            result=(window_probe or _browser_window)()
            if not result:return False
            window,still_active=result
            name=window.window_text()
            if 'youtube' not in name.lower() or title=='فيديو يوتيوب' or title[:30].casefold() not in name.casefold():return False
            if bound_handle is None:bound_handle=window.handle
            if window.handle!=bound_handle:return False
            controls=window.descendants(control_type='Button')[:250]
            play=None
            for control in controls:
                label=control.window_text().strip().casefold()
                if label in PAUSE and still_active() and time.monotonic()<deadline:return True
                if label in PLAY:play=control
            if play is not None and not clicked and still_active() and time.monotonic()<deadline:
                # Refresh actual consent immediately before a native action.
                from computer_control.api import load_policy
                current=load_policy() if window_probe is None else policy
                if not current.enabled or current.evaluate('invoke_ui',{'target_name':'Play video'})[1]!=Decision.ALLOW:return False
                play.invoke();clicked=True
        except Exception:return False
        time.sleep(.3)
    return False
