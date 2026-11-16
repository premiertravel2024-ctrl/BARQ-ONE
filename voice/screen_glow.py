"""Windows-only click-through burgundy screen-edge indicator for spoken BARQ audio.

Native Win32 windows, no new pip dependencies. Windows at the edges are not
focusable and never accept mouse input. They appear ONLY while output is playing;
the backend playback lease expires even if the webview crashes.
"""
from __future__ import annotations

import math
import os
import threading
import time


def edge_rectangles(x: int, y: int, width: int, height: int, thickness: int):
    """Four thin strips, anchored to the virtual Windows desktop bounds."""
    if width <= 0 or height <= 0 or thickness <= 0:
        return ()
    t = min(thickness, width, height)
    return ((x, y, width, t), (x, y+height-t, width, t),
            (x, y+t, t, max(0,height-2*t)),
            (x+width-t, y+t, t, max(0,height-2*t)))


class _WindowsGlow:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.c = ctypes
        self.w = wintypes
        user = ctypes.windll.user32
        gdi = ctypes.windll.gdi32
        # Native HANDLE/GDI pointers are 64-bit on x64 Windows. The ctypes
        # defaults (c_int) truncate them, which may terminate the whole EXE.
        gdi.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        gdi.CreateSolidBrush.restype = wintypes.HBRUSH
        gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi.DeleteObject.restype = wintypes.BOOL
        user.RegisterClassW.restype = wintypes.ATOM
        user.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user.UnregisterClassW.restype = wintypes.BOOL
        user.DestroyWindow.argtypes = [wintypes.HWND]
        user.DestroyWindow.restype = wintypes.BOOL
        self.user = user
        self.gdi = gdi
        self.wnd_proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND,
                                           wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)(self._dispatch)
        class WindowClass(ctypes.Structure):
            _fields_ = [('style',wintypes.UINT),('lpfnWndProc',ctypes.c_void_p),
                        ('cbClsExtra',ctypes.c_int),('cbWndExtra',ctypes.c_int),
                        ('hInstance',wintypes.HINSTANCE),('hIcon',wintypes.HICON),
                        ('hCursor',wintypes.HANDLE),('hbrBackground',wintypes.HBRUSH),
                        ('lpszMenuName',wintypes.LPCWSTR),('lpszClassName',wintypes.LPCWSTR)]
        self.class_name = 'BARQVoiceRedEdgeGlowV1'
        self.brush = gdi.CreateSolidBrush(0x002B0D78) # Burgundy #780D2B in Win32 BGR
        wc = WindowClass()
        wc.lpfnWndProc=ctypes.cast(self.wnd_proc, ctypes.c_void_p).value
        ctypes.windll.kernel32.GetModuleHandleW.restype=wintypes.HINSTANCE
        self.instance=ctypes.windll.kernel32.GetModuleHandleW(None)
        wc.hInstance=self.instance
        wc.hbrBackground=self.brush
        wc.lpszClassName=self.class_name
        self.class_atom = user.RegisterClassW(ctypes.byref(wc))
        if not self.class_atom:
            raise OSError(ctypes.get_last_error(), 'Could not register BARQ red glow class')
        self.windows=[]
        user.CreateWindowExW.restype=wintypes.HWND
        user.CreateWindowExW.argtypes=[wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        user.DefWindowProcW.restype=ctypes.c_ssize_t
        user.DefWindowProcW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        user.SetLayeredWindowAttributes.argtypes=[wintypes.HWND,wintypes.COLORREF,wintypes.BYTE,wintypes.DWORD]
        user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                                    ctypes.c_int,ctypes.c_int,wintypes.UINT]

    def _dispatch(self, hwnd, message, wp, lp):
        if message==0x84: # WM_NCHITTEST, never consume clicks
            return -1 # HTTRANSPARENT
        return self.user.DefWindowProcW(hwnd,message,wp,lp)

    def _bounds(self):
        # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
        return tuple(self.user.GetSystemMetrics(i) for i in (76,77,78,79))

    def _monitor_bounds(self):
        # Separate halos for landscape/portrait monitors, including negative coordinates.
        bounds=[]
        callback_type=self.c.WINFUNCTYPE(self.w.BOOL,self.w.HANDLE,self.w.HDC,self.c.POINTER(self.w.RECT),self.w.LPARAM)
        def visit(_monitor,_dc,rectangle,_data):
            r=rectangle.contents
            bounds.append((r.left,r.top,r.right-r.left,r.bottom-r.top))
            return True
        callback=callback_type(visit)
        self.user.EnumDisplayMonitors.argtypes=[self.w.HDC,self.c.c_void_p,callback_type,self.w.LPARAM]
        self.user.EnumDisplayMonitors(None,None,callback,0)
        return bounds or [self._bounds()]

    def make_windows(self):
        self.remove_windows()
        # Translucent bands soften the burgundy light inward without a full-screen surface.
        for x,y,width,height in self._monitor_bounds():
          for thickness,alpha in ((44,10),(28,18),(16,30),(8,48),(3,92)):
            for left,top,w,h in edge_rectangles(x,y,width,height,thickness):
                if w<=0 or h<=0:continue
                hwnd=self.user.CreateWindowExW(
                    0x00080000|0x00000020|0x00000080|0x08000000, # layered/transparent/tool/noactivate
                    self.class_name, '',0x80000000, left,top,w,h,
                    None,None,self.instance,None)
                if hwnd:
                    self.user.SetLayeredWindowAttributes(hwnd,0,alpha,0x2)
                    self.windows.append((hwnd,alpha,left,top,w,h))

    def show(self, alpha_scale:float):
        if not self.windows:self.make_windows()
        for hwnd,alpha,left,top,w,h in self.windows:
            self.user.SetLayeredWindowAttributes(hwnd,0,int(max(0,min(255,alpha*alpha_scale))),0x2)
            self.user.SetWindowPos(hwnd, -1,left,top,w,h,0x0010|0x0040) # SWP_NOACTIVATE|SWP_SHOWWINDOW

    def remove_windows(self):
        for hwnd,*_ in self.windows:
            self.user.DestroyWindow(hwnd)
        self.windows=[]

    def pump(self):
        from ctypes import wintypes
        class Point(self.c.Structure):
            _fields_=[('x',self.c.c_long),('y',self.c.c_long)]
        class Msg(self.c.Structure):
            _fields_=[('hwnd',wintypes.HWND),('message',wintypes.UINT),('wParam',wintypes.WPARAM),
                      ('lParam',wintypes.LPARAM),('time',wintypes.DWORD),('pt',Point),('lPrivate',wintypes.DWORD)]
        msg=Msg()
        while self.user.PeekMessageW(self.c.byref(msg),None,0,0,1):
            self.user.TranslateMessage(self.c.byref(msg))
            self.user.DispatchMessageW(self.c.byref(msg))

    def close(self):
        self.remove_windows()
        # Never leave a class registered with a WNDPROC callback whose Python
        # owner has been collected: Windows can call a dangling function pointer
        # on a later speaking turn and crash the whole process (0xC0000005).
        if getattr(self, 'class_atom', 0):
            self.user.UnregisterClassW(self.class_name, self.instance)
            self.class_atom = 0
        if self.brush:
            self.gdi.DeleteObject(self.brush)
            self.brush = None


def run_glow(stop:threading.Event, is_speaking):
    """Keep the WNDPROC callback alive through *every* speaking/silent cycle.

    Previously the code created a new _WindowsGlow on each utterance. The
    Win32 class name survived when its Python callback was garbage collected,
    potentially causing an access violation and an immediate BARQ.exe exit.
    """
    if os.name!='nt':return
    overlay=None
    try:
        while not stop.is_set():
            try:
                if is_speaking():
                    if overlay is None:overlay=_WindowsGlow()
                    overlay.show(.89+.11*math.sin(time.monotonic()*5.0))
                elif overlay is not None:
                    overlay.remove_windows()  # keep registered callback alive
                if overlay is not None:overlay.pump()
            except (OSError, ValueError, RuntimeError) as exc:
                # The decoration is optional: a failed overlay must never be
                # allowed to tear down the voice/desktop process.
                import logging
                logging.getLogger(__name__).warning('Red glow disabled: %s',type(exc).__name__)
                break
            stop.wait(.09)
    finally:
        if overlay is not None:overlay.close()
