"""Opt-in Arabic 'يا برق' wake detector using a user-installed OFFLINE Vosk model.

Audio samples never leave the computer. This only wakes the regular BARQ Live
conversation UI; all desktop execution still goes through audited computer tools.
"""
from __future__ import annotations
import ctypes
import audioop
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

MODEL_NAME='vosk-model-ar-mgb2-0.4'
STATE=Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'AI Router Agent'
# Prefer visible install-folder models, but recognize models from older
# releases without silently copying/removing users' existing downloads.
_APP=(Path(sys.executable).resolve().parent if getattr(sys,'frozen',False)
      else Path(__file__).resolve().parents[1])
_PACKAGED_MODEL=_APP/'models'/'wake'/MODEL_NAME
_LEGACY_MODEL=STATE/'wake_models'/MODEL_NAME
MODEL=(_PACKAGED_MODEL if (_PACKAGED_MODEL/'am').is_dir() and (_PACKAGED_MODEL/'conf').is_dir()
       else _LEGACY_MODEL if (_LEGACY_MODEL/'am').is_dir() and (_LEGACY_MODEL/'conf').is_dir()
       else _PACKAGED_MODEL)

DISCOVERY=STATE / 'wake_endpoint.json'
STOP=threading.Event()
PAUSED=threading.Event()
OPENER=build_opener(ProxyHandler({}))
HEADLESS = '--headless' in sys.argv
_last_wake_time = 0.0
_DIAG = {'level':0, 'audio_seen':False, 'last_audio_at':0, 'input_device':'', 'input_devices':[], 'heard_speech':False}

def report(state: str, detail: str = ''):
    """Tiny heartbeat only. No microphone audio or recognized sentences persist."""
    target = STATE / 'wake_status.json'
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.tmp')
        tmp.write_text(json.dumps({'state':state,'detail':detail[:180],
            'last_wake':_last_wake_time,'updated':time.time(),**_DIAG},ensure_ascii=False),encoding='utf-8')
        os.replace(tmp,target)
    except OSError:
        pass


def message(text: str):
    if os.name=='nt':
        ctypes.windll.user32.MessageBoxW(None,text,'BARQ Wake',0x40)
    else:print(text)


def endpoint():
    try:
        data=json.loads(DISCOVERY.read_text(encoding='utf-8'))
        port=int(data.get('port',0))
        if not 1<=port<=65535 or not isinstance(data.get('token'),str):return None
        return data
    except (OSError,ValueError,TypeError):return None


def live_active(data):
    if not data:return False
    try:
        with OPENER.open(f"http://127.0.0.1:{data['port']}/v1/voice/wake/session", timeout=1) as res:
            return bool(json.load(res).get('live_active'))
    except (OSError,ValueError):return False


def activate_window():
    if os.name!='nt':return
    try:
        hwnd=ctypes.windll.user32.FindWindowW(None,'BARQ')
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd,9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except (OSError,AttributeError):pass


def ensure_barq_running():
    """Wake may start the installed desktop UI; it never starts arbitrary apps."""
    data=endpoint()
    if data and ping_barq(data):return data
    # A frozen wake helper lives beside the installed BARQ.exe.
    exe=(Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'BARQ.exe'
    if not exe.is_file():return None
    try:subprocess.Popen([str(exe)],cwd=str(exe.parent))
    except OSError:return None
    for _ in range(60):
        if STOP.is_set():break
        STOP.wait(.25)
        data=endpoint()
        if data and ping_barq(data):return data
    return None


def ping_barq(data):
    try:
        with OPENER.open(f"http://127.0.0.1:{data['port']}/v1/voice/wake/session", timeout=1) as res:
            return res.status==200
    except (OSError,ValueError):return False


def send_wake():
    data=ensure_barq_running()
    if not data:return False
    body=json.dumps({'phrase':'يا برق'},ensure_ascii=False).encode('utf-8')
    req=Request(f"http://127.0.0.1:{data['port']}/v1/voice/wake/trigger",data=body,method='POST',headers={
        'Content-Type':'application/json; charset=utf-8','X-BARQ-WAKE-TOKEN':data['token']})
    try:
        with OPENER.open(req,timeout=3) as res:
            result=json.load(res)
        if result.get('queued'):
            activate_window()
            return True
    except (OSError,ValueError):pass
    return False


def is_arabic_wake(text: str) -> bool:
    """A short, complete wake phrase, never an arbitrary conversation mention."""
    clean=re.sub(r'[\u064b-\u065f\u0670\u0640]', '', str(text))
    clean=re.sub(r'[^\w\s\u0600-\u06ff]',' ',clean).strip()
    words=clean.split()
    return 1<=len(words)<=3 and any(word in ('برق','برك','بارق') for word in words) and (len(words)==1 or 'يا' in words)



def contains_wake_prefix(text: str) -> bool:
    """Recognize 'ya BARQ' at the beginning of a short utterance.

    Vosk frequently keeps listening after 'ya barq' and returns extra words.
    Keep a strict prefix and reject common false sounds (e.g. 'بلاء').
    """
    clean=re.sub(r'[\u064b-\u065f\u0670\u0640]', '', str(text))
    clean=re.sub(r'[^\w\s\u0600-\u06ff]', ' ', clean).strip().lower()
    words=clean.split()
    if not words or len(words)>10:return False
    # In Egyptian Arabic the last letter of برق is pronounced as a glottal stop.
    variants={'برق','برء','برأ','برك','بارق','براق'}
    return (len(words)>=2 and words[0]=='يا' and words[1] in variants) or (len(words)==1 and words[0] in variants)


def wake_recognized(text: str) -> bool:
    return is_arabic_wake(text) or contains_wake_prefix(text)


def preferred_input_device():
    """Explicit mic choice is stored only when the user selects one in BARQ."""
    try:
        settings=json.loads((STATE/'wake_preferences.json').read_text(encoding='utf-8'))
        chosen=settings.get('input_device')
        return chosen if type(chosen) is int and 0<=chosen<=255 else None
    except (OSError,ValueError,TypeError):return None

def icon_image(paused=False):
    from PIL import Image, ImageDraw
    image=Image.new('RGB',(64,64),'#0F1115')
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((4,4,60,60),radius=16,outline='#6A2029' if paused else '#FF2446',width=4)
    draw.text((24,21),'B',fill='#FFFFFF')
    return image


def listen_loop(icon):
    global _last_wake_time
    try:
        import sounddevice as sd
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        report('loading','Loading Arabic recognition model')
        model=Model(str(MODEL))
        cooldown=0.0
        try:
            available=[{'id':i,'name':str(d['name'])[:90]} for i,d in enumerate(sd.query_devices())
                       if int(d.get('max_input_channels',0))>0]
        except Exception:
            # Device enumeration is optional; default recording may still work.
            available=[]
        _DIAG['input_devices']=available[:80]
        while not STOP.is_set():
            if PAUSED.is_set() or time.monotonic()<cooldown or live_active(endpoint()):
                report('paused' if PAUSED.is_set() else 'waiting','Wake microphone released for live call' if not PAUSED.is_set() else '')
                STOP.wait(0.7)
                continue
            pieces=queue.Queue(maxsize=24)
            recognizer=KaldiRecognizer(model,16000)
            last_status=time.monotonic()
            # Many Windows audio devices do NOT support recording at exactly 16kHz.
            # Capture at the native rate, resample locally to 16kHz for Vosk.
            device_index=preferred_input_device()
            device=sd.query_devices(device=device_index,kind='input')
            _DIAG['input_device']=str(device.get('name',''))[:90]
            _DIAG.update(level=0,audio_seen=False,heard_speech=False,last_audio_at=0)
            native_rate=int(device.get('default_samplerate') or 16000)
            if native_rate < 8000 or native_rate > 192000:
                native_rate=16000
            resample_state=None
            partial_hits=0
            def callback(indata,frames,time_info,status):
                if not STOP.is_set():
                    try:pieces.put_nowait(bytes(indata))
                    except queue.Full:pass
            try:
                with sd.RawInputStream(device=device_index,samplerate=native_rate,blocksize=max(1024,native_rate//4),dtype='int16',channels=1,callback=callback):
                    report('listening','Microphone active; listening for يا برق')
                    detected=False
                    while not STOP.is_set() and not PAUSED.is_set():
                        if time.monotonic()-last_status>=3:
                            last_status=time.monotonic()
                            if live_active(endpoint()):break
                            report('listening','Microphone active; listening for يا برق')
                        try:pcm=pieces.get(timeout=.45)
                        except queue.Empty:continue
                        # Meters are numerical only: no audio or transcript is saved.
                        level=min(100,round(audioop.rms(pcm,2)*500/32768))
                        _DIAG['level']=level
                        _DIAG['audio_seen']=True
                        if level>=3:
                            _DIAG['last_audio_at']=time.time()
                            _DIAG['heard_speech']=True
                        if native_rate!=16000:
                            pcm,resample_state=audioop.ratecv(pcm,2,1,native_rate,16000,resample_state)
                        if recognizer.AcceptWaveform(pcm):
                            result=json.loads(recognizer.Result()).get('text','')
                            partial_hits=0
                            if wake_recognized(result):
                                detected=True
                                break
                        else:
                            # Short wake words are often only delivered as partial
                            # results on Vosk, never a finalized full sentence.
                            partial=json.loads(recognizer.PartialResult()).get('partial','')
                            partial_hits=partial_hits+1 if wake_recognized(partial) else 0
                            if partial_hits>=3:
                                detected=True
                                break
                if detected:
                    report('activating','Wake phrase detected; opening BARQ')
                    activated=send_wake()
                    cooldown=time.monotonic()+(15 if activated else 3)
                    if activated:
                        _last_wake_time=time.time()
                        report('activated','Voice call requested')
                    else:
                        report('error','BARQ did not accept wake activation; open BARQ first')
                    icon.title='BARQ: voice call requested' if activated else 'BARQ: open the app first'
            except Exception as exc:
                logging.exception('Microphone stream unavailable')
                report('error',f'Microphone: {type(exc).__name__}: {str(exc)[:100]}')
                STOP.wait(3)
    except Exception as exc:
        logging.exception('Arabic wake recognizer failed')
        report('error',f'Voice model: {type(exc).__name__}: {str(exc)[:100]}')
        if not HEADLESS:
            message('مساعد برق مش قادر يفتح الميكروفون أو نموذج Vosk. شغّل INSTALL_ARABIC_WAKE.bat وراجع إعدادات الميكروفون.')
        STOP.set()
        icon.stop()


class HiddenIcon:
    title = ''
    def stop(self):
        STOP.set()


def headless():
    """Launched and controlled solely from BARQ Settings. No second tray app."""
    if os.name!='nt':return 2
    if not (MODEL/'am').is_dir() or not (MODEL/'conf').is_dir():
        report('error','Arabic Vosk model is missing from BARQ/models/wake')
        return 2
    mutex=ctypes.windll.kernel32.CreateMutexW(None,True,'Local\\BARQ-Wake-Listener')
    if not mutex:return 2
    try:
        if ctypes.windll.kernel32.GetLastError()==183:
            report('error','Another wake listener is already running: close old tray app')
            return 3
        report('starting','Starting internal wake listener')
        listen_loop(HiddenIcon())
        return 0
    finally:
        ctypes.windll.kernel32.ReleaseMutex(mutex)
        ctypes.windll.kernel32.CloseHandle(mutex)

def main():
    if os.name!='nt':raise SystemExit('Wake listener requires Windows')
    if not (MODEL/'am').is_dir() or not (MODEL/'conf').is_dir():
        message('نموذج التنبيه العربي مش مثبت. شغّل INSTALL_ARABIC_WAKE.bat مرة واحدة الأول.')
        return 2
    try:
        import pystray
        import sounddevice
        import vosk
        from PIL import Image
    except ImportError:
        message('مكتبات التعرف الصوتي ناقصة. شغّل INSTALL_ARABIC_WAKE.bat الأول.')
        return 2
    mutex=ctypes.windll.kernel32.CreateMutexW(None,True,'Local\\BARQ-Wake-Listener')
    if not mutex:raise SystemExit('Could not lock wake listener')
    if ctypes.windll.kernel32.GetLastError()==183:
        ctypes.windll.kernel32.CloseHandle(mutex)
        return 0
    # No command line or network voice listening is started without an explicit
    # user-run launcher. Tray allows immediate pause/exit at all times.
    def pause(icon,item):
        if PAUSED.is_set():PAUSED.clear();icon.title='BARQ: listening for يا برق';icon.icon=icon_image()
        else:PAUSED.set();icon.title='BARQ: microphone paused';icon.icon=icon_image(True)
    def exit_icon(icon,item):STOP.set();icon.stop()
    icon=pystray.Icon('barq-ar-wake',icon_image(),'BARQ: listening for يا برق',menu=pystray.Menu(
        pystray.MenuItem('إيقاف/استئناف الميكروفون',pause),
        pystray.MenuItem('إغلاق المساعد الصوتي',exit_icon)))
    worker=threading.Thread(target=listen_loop,args=(icon,),daemon=True)
    worker.start()
    try:icon.run()
    finally:
        STOP.set()
        worker.join(timeout=5)
        ctypes.windll.kernel32.ReleaseMutex(mutex)
        ctypes.windll.kernel32.CloseHandle(mutex)
    return 0


if __name__=='__main__':
    if '--headless' in sys.argv:
        raise SystemExit(headless())
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':
        # Packaged-app smoke gate, with no network or microphone access.
        import importlib
        for package in ('vosk','sounddevice','pystray','PIL'):
            importlib.import_module(package)
        print('BARQ_WAKE_RUNTIME_OK',flush=True)
        raise SystemExit(0)
    if len(sys.argv)>1 and sys.argv[1] in ('--install-model', '--install-model-from-archive'):
        # Inno Setup performs the download with an integrated progress bar, then
        # launches this helper hidden to unpack the downloaded archive.
        from scripts.install_arabic_wake import install
        local_archive = None
        if sys.argv[1] == '--install-model-from-archive':
            if len(sys.argv)!=3:
                raise SystemExit(2)
            local_archive=sys.argv[2]
        try:
            install(archive_path=local_archive)
        except (OSError, ValueError, EOFError, RuntimeError) as exc:
            logging.exception('Arabic wake model extraction failed: %s',exc)
            raise SystemExit(1)
        raise SystemExit(0)
    raise SystemExit(main())
