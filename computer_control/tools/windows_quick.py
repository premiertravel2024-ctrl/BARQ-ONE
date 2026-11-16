"""Safe Windows desktop convenience controls.

No shell or administrative token. Explicit user opt-in is enforced by the
Manager before any of these methods are called. No registry changes.
"""
from __future__ import annotations
import os

SETTINGS_PAGES={
    'display':'display','sound':'sound','bluetooth':'bluetooth',
    'network':'network-status','apps':'appsfeatures',
    'microphone':'privacy-microphone','windowsupdate':'windowsupdate',
}

def set_volume(percent:int)->dict:
    from pycaw.pycaw import AudioUtilities
    speakers=AudioUtilities.GetSpeakers()
    if speakers is None:raise RuntimeError('Windows audio output is unavailable')
    speakers.volume_percent=percent
    return {'ok':True,'percent':round(float(speakers.volume_percent)), 'action':'set_volume'}

def get_volume()->dict:
    from pycaw.pycaw import AudioUtilities
    speakers=AudioUtilities.GetSpeakers()
    if speakers is None:raise RuntimeError('Windows audio output is unavailable')
    return {'percent':round(float(speakers.volume_percent))}

def set_brightness(percent:int)->dict:
    import screen_brightness_control as sbc
    try:
        sbc.set_brightness(percent,display=0)
        actual=sbc.get_brightness(display=0)
    except Exception as exc:
        raise RuntimeError('Display brightness is not supported by the active monitor/driver') from exc
    return {'ok':True,'percent':int(actual[0] if isinstance(actual,list) else actual),'action':'set_brightness'}

def get_brightness()->dict:
    import screen_brightness_control as sbc
    try:actual=sbc.get_brightness(display=0)
    except Exception as exc:raise RuntimeError('Brightness cannot be read for this monitor') from exc
    return {'percent':int(actual[0] if isinstance(actual,list) else actual)}

def open_windows_settings(page:str)->dict:
    if page not in SETTINGS_PAGES:raise ValueError('Unsupported Settings page')
    if os.name!='nt':raise RuntimeError('Windows required')
    os.startfile('ms-settings:'+SETTINGS_PAGES[page])
    return {'ok':True,'page':page,'action':'open_windows_settings'}
