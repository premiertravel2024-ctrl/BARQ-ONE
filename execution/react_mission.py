"""Deterministic first-party React setup from chat or voice.

Only invoked on a precise end-to-end user request. NEVER accepts raw commands
from the language model; grant scopes are held in UI-owned local JSON.
"""
from __future__ import annotations
import json,os,sys,threading,time,uuid
from pathlib import Path
from typing import Any, Callable
from .runner import Command,Runner
from .services import ServiceManager
from .grants import GrantStore
from .known_folders import known_folder
from .recipes import scaffold_react,install_and_build,start_react
from computer_control.safety.policy import redact,Mode
from computer_control.state_store import TaskStateStore


def is_react_desktop_goal(goal:str)->bool:
    text=(goal or '').casefold().replace('أ','ا').replace('إ','ا').replace('آ','ا')
    return any(w in text for w in ('react','رياكت','ريآكت','ريأكت')) and any(
        w in text for w in ('desktop','ديسكتوب','سطح المكتب')) and any(
        w in text for w in ('اعمل','انشئ','ابني','create','build','make'))

def _vscode_window_visible(project:Path)->bool:
    """Observe the real editor window; launching a CLI alone proves nothing."""
    from computer_control.adapters.desktop import default_adapter
    windows=default_adapter().perceive().windows
    return any(project.name.casefold() in str(window).casefold() for window in windows)


class ReactMission:
    """In-process mission; survives model failure during a tick, not app restarts."""
    def __init__(self, *, window_probe:Callable[[Path],bool]|None=None, window_probe_timeout:float=6.0):
        self._lock=threading.RLock()
        self.current=None
        self._worker=None
        self.cancelled=threading.Event()
        self.services=ServiceManager()
        # Inject the window observation for unit tests: they must never probe
        # the real desktop, which can be slow or blocked by Windows UIA.
        self._window_probe=window_probe or _vscode_window_visible
        self._window_probe_timeout=max(0.1,min(10.0,float(window_probe_timeout)))

    def public(self)->dict|None:
        with self._lock:
            if self.current is None:return None
            return json.loads(json.dumps(self.current,ensure_ascii=False))

    def _record(self,step:str,status:str,message:str='',proof:dict|None=None):
        with self._lock:
            item=self.current
            if item is None:return
            item['history'].append({'tool':step,'status':status,'verification':'verified' if status=='committed' else 'unverified',
                                    'verification_reason':redact(message)[:240], 'evidence':proof or {}})
            item['progress']=sum(x['status']=='committed' for x in item['history'])
            item['phase']='verify' if status=='committed' else 'execute'
            item['message']=redact(message)[:300]

    def _run(self,goal:str,grants:GrantStore,target:Path):
        task_id=self.current['id']
        ledger=TaskStateStore()
        project=None
        try:
            steps=('scaffold','install_and_build','vscode','start_server')
            runner=Runner()
            for i,step in enumerate(steps):
                if self.cancelled.is_set():raise InterruptedError('Stopped by user')
                digest=__import__('hashlib').sha256((str(target)+step).encode()).hexdigest()
                ledger.step_started(task_id,str(i),step,digest,digest[:24])
                try:
                    if step=='scaffold':
                        outcome=scaffold_react(target,grants,name='barq-react-'+uuid.uuid4().hex[:6])
                        project=Path(outcome['path'])
                        verified=project.is_dir() and (project/'package.json').exists()
                    elif step=='install_and_build':
                        outcome=install_and_build(project,grants,runner,cancel=self.cancelled)
                        verified=(project/'dist'/'index.html').is_file()
                    elif step=='vscode':
                        if not grants.permits(str(project),'read'):
                            raise PermissionError('VS Code project read grant required')
                        # The code CLI is optional and may legitimately be absent.
                        binary,argv,cwd=runner.validate(Command('code',(str(project),),cwd=str(project)))
                        import subprocess
                        proc=subprocess.Popen(argv,cwd=str(project),stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        outcome={'requested_app':'VS Code','project':str(project),'pid':proc.pid}
                        # Verify the actual window, NOT the CLI's exit status.
                        verified=False
                        # Window enumeration on real Windows can take seconds, and
                        # should never block the mission indefinitely. The probe
                        # runs once in a daemon worker with a finite budget; a
                        # timeout means NEEDS_REVIEW, never a claimed success.
                        def check_window():
                            try:
                                deadline=time.monotonic()+self._window_probe_timeout
                                while not self.cancelled.is_set():
                                    try:
                                        if self._window_probe(project):
                                            observed[0]=True
                                            break
                                    except Exception:
                                        # UIA may not be available on this desktop.
                                        break
                                    remaining=deadline-time.monotonic()
                                    if remaining<=0:break
                                    self.cancelled.wait(timeout=min(0.4,remaining))
                            finally:
                                probe_done.set()
                        observed=[False]
                        probe_done=threading.Event()
                        threading.Thread(target=check_window,daemon=True,
                                         name='BARQ-vscode-window-probe').start()
                        if probe_done.wait(timeout=self._window_probe_timeout+0.1) and not self.cancelled.is_set():
                            verified=observed[0]
                        if self.cancelled.is_set():
                            raise InterruptedError('Stopped by user')
                    else:
                        outcome=start_react(project,grants,self.services,cancel=self.cancelled)
                        verified=outcome.get('http_status')==200
                        if verified:
                            import webbrowser
                            try:outcome['browser_open_requested']=bool(webbrowser.open(outcome['url']))
                            except Exception:outcome['browser_open_requested']=False
                    if verified:
                        ledger.step_finished(task_id,str(i),'committed','verified')
                        self._record(step,'committed','اتأكدت إن الخطوة نجحت.',outcome)
                    else:
                        ledger.step_finished(task_id,str(i),'failed','needs_review')
                        self._record(step,'needs_review','الأمر اتبعت لكن مفيش دليل كافي إن النافذة اتفتحت.',outcome)
                except Exception:
                    try:ledger.step_finished(task_id,str(i),'failed','failed')
                    except ValueError:pass
                    raise
            with self._lock:
                item=self.current
                item['status']='needs_review' if any(x['status']!='committed' for x in item['history']) else 'completed'
                item['phase']='verify'
                item['message']=('المشروع شغال وHTTP 200 مؤكد؛ فتح نافذة VS Code محتاج تحقق بصري.'
                                 if item['status']!='completed' else 'المشروع شغال ونتيجة فتح VS Code وHTTP تم التحقق منها.')
                item['goal_proof']={'status':'unverified' if item['status']!='completed' else 'verified',
                                    'reason':('VS Code window not independently observed; HTTP was verified'
                                              if item['status']!='completed' else 'VS Code window and local HTTP 200 verified')}
        except InterruptedError:
            self.services.close()
            with self._lock:self.current.update(status='stopped',message='المهمة اتوقفت بأمرك',phase='verify')
        except Exception as exc:
            self.services.close()
            with self._lock:self.current.update(status='failed',message=redact(str(exc))[:300],phase='verify')

    def start(self,goal:str,source:str,enabled:bool,mode:Mode)->dict:
        if sys.platform!='win32':raise RuntimeError('This workflow must run on Windows')
        if not enabled or mode==Mode.OBSERVE:
            raise RuntimeError('Enable Computer Control with an active permission mode first')
        target=known_folder('desktop')
        grants=GrantStore()
        required=('read','create','write','install_dependencies','build','run_dev_server')
        missing=[scope for scope in required if not grants.permits(str(target/'barq-react-project'),scope)]
        if missing:
            return {'status':'needs_project_grant','message':'اختار Desktop من صلاحيات المشاريع الأول. الصلاحيات المطلوبة: '+', '.join(missing),
                    'missing_scopes':missing,'executed':False}
        with self._lock:
            if self.current and self.current['status'] in ('planning','running'):
                raise RuntimeError('A React setup mission is already running')
            if self.current:
                TaskStateStore().save({**self.current,'model':'auto'})
            self.cancelled.clear()
            self.current={'id':uuid.uuid4().hex,'goal':goal[:3000],'status':'planning',
                          'source':source,'started':time.monotonic(),'phase':'plan','steps':['إنشاء مشروع React','تثبيت الاعتمادات والبناء',
                          'فتح VS Code','تشغيل الخادم والتحقق HTTP 200'],
                          'progress':0,'failures':0,'pending':None,'history':[],
                          'goal_proof':{'status':'unverified','reason':'Not yet executed'},
                          'message':'بجهز الخطوات في Desktop المعتمد'}
            value=self.public()
            self._worker=threading.Thread(target=self._run,args=(goal,grants,target),daemon=True,
                                          name='BARQ-react-mission')
            self.current['status']='running'
            self._worker.start()
            return value | {'status':'running'}

    def stop(self)->dict:
        self.cancelled.set()
        self.services.close()
        return {'stopped':True}

_MISSION=ReactMission()
def mission()->ReactMission:return _MISSION
