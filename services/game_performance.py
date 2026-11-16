"""On-demand PresentMon ETW samples. Never infer FPS from refresh rate/CPU load."""
from __future__ import annotations
import csv,hashlib,io,math,os,subprocess,sys,tempfile,threading,uuid
from collections import defaultdict
from pathlib import Path
from core.paths import resource
VERSION='2.6.0'
SHA256='b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af'
_capture_lock=threading.Lock()
EXCLUDED={'barq.exe','python.exe','pythonw.exe','dwm.exe','explorer.exe','msedge.exe','chrome.exe','firefox.exe','msedgewebview2.exe','presentmon-2.6.0-x64.exe'}

def summarize_csv(text:str,*,pid:int|None=None)->dict:
    groups=defaultdict(list)
    for row in csv.DictReader(io.StringIO(text.lstrip('\ufeff'))):
        row={str(k).lower():v for k,v in row.items() if k}
        try:
            process=int(row.get('processid',''));name=Path(row.get('application','').replace('\\','/')).name
            if name.lower() in EXCLUDED or (pid is not None and process!=pid):continue
            value=float(row.get('msbetweenpresents',''))
            if not math.isfinite(value) or value<=0 or value>60000:continue
            groups[(name,process,row.get('swapchainaddress',''))].append(value)
        except (TypeError,ValueError):continue
    # Keep one busiest swapchain PER process. Never merge unrelated windows or games.
    processes={}
    for (name,process,swap),values in groups.items():
        if len(values)<10:continue
        if process not in processes or len(values)>len(processes[process][1]):processes[process]=(name,values)
    if not processes:return {'status':'unavailable','message':'مفيش عينة فريمات صالحة. خلي اللعبة شغالة وفي المقدمة وجرّب تاني.'}
    if len(processes)>1:return {'status':'choose','message':'رصدت أكتر من برنامج بيرسم فريمات. خلي اللعبة في المقدمة واطلب القياس صوتيًا لتحديدها.','applications':[name for name,_ in processes.values()]}
    process,(name,values)=next(iter(processes.items()))
    slow=sorted(values,reverse=True)[:max(1,math.ceil(len(values)*.01))]
    fps=1000*len(values)/sum(values);low=1000*len(slow)/sum(slow) if len(values)>=100 else None
    return {'status':'ok','application':name,'pid':process,'average_fps':round(fps,1),'one_percent_low':round(low,1) if low else None,
            'samples':len(values),'sample_seconds':round(sum(values)/1000,2),'metric':'presented_fps','source':'PresentMon 2.6.0 ETW',
            'message':f'{name}: متوسط {fps:.1f} FPS'+(f'، و1% Low حوالي {low:.1f} FPS.' if low else '؛ العينة قصيرة لحساب 1% Low موثوق.')}

def presentmon_path()->Path|None:
    candidates=[resource('tools','presentmon','PresentMon-2.6.0-x64.exe'),Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'Bq/tools/presentmon/PresentMon-2.6.0-x64.exe']
    for path in candidates:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==SHA256:return path
    return None

def foreground_pid()->int|None:
    if sys.platform!='win32':return None
    import ctypes
    from ctypes import wintypes
    user=ctypes.windll.user32;user.GetForegroundWindow.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    pid=wintypes.DWORD();user.GetWindowThreadProcessId(user.GetForegroundWindow(),ctypes.byref(pid))
    try:
        import psutil
        return pid.value if psutil.Process(pid.value).name().lower() not in EXCLUDED else None
    except Exception:return None

def capture_fps(*,runner=subprocess.run,tool:Path|None=None,pid:int|None=None)->dict:
    if sys.platform!='win32':return {'status':'unsupported','message':'قياس الفريمات متاح على Windows فقط.'}
    tool=tool or presentmon_path()
    if not tool:return {'status':'missing_tool','message':'أداة قياس الفريمات مش جاهزة. شغّل INSTALL_BARQ_FPS.bat مرة واحدة.'}
    if not _capture_lock.acquire(blocking=False):return {'status':'busy','message':'في قياس فريمات شغال بالفعل؛ استنى نتيجته.'}
    try:
        target=pid if pid is not None else foreground_pid()
        with tempfile.TemporaryDirectory(prefix='barq-fps-') as folder:
            path=Path(folder)/'frames.csv'
            args=[str(tool),'--output_file',str(path),'--v1_metrics','--timed','5','--terminate_after_timed','--no_console_stats','--session_name','BARQ-'+uuid.uuid4().hex]
            if target is not None:args+=['--process_id',str(target)]
            result=runner(args,shell=False,capture_output=True,timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode!=0:return {'status':'unavailable','message':'ويندوز لم يسمح ببدء قياس PresentMon. قد تحتاج صلاحية Performance Log Users أو تشغيل برق كمسؤول للقياس؛ مفيش أرقام مؤكدة.'}
            if not path.is_file() or path.stat().st_size>12_000_000:return {'status':'unavailable','message':'القياس ما رجعش سجل فريمات صالح.'}
            return summarize_csv(path.read_text(encoding='utf-8-sig',errors='replace'),pid=target)
    except (OSError,subprocess.TimeoutExpired):return {'status':'unavailable','message':'قياس الفريمات انتهى بدون عينة مؤكدة. جرّب واللعبة شغالة.'}
    finally:_capture_lock.release()
