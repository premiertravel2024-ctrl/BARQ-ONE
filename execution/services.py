"""Bounded foreground-owned dev-server manager. Background services end with BARQ."""
from __future__ import annotations
import os,socket,subprocess,threading,time,urllib.error,urllib.request
from pathlib import Path
from .runner import Runner,Command,CommandRejected,_WindowsJob


def choose_port(host='127.0.0.1')->int:
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind((host,0))
        return sock.getsockname()[1]

class ServiceManager:
    def __init__(self,runner:Runner|None=None):
        self.runner=runner or Runner()
        self._services={}
        self._lock=threading.RLock()

    def start(self,name:str,spec:Command,*,port:int,log_file:Path,wait_seconds=35,cancel=None)->dict:
        if not 1024<=port<=65535:raise ValueError('Unsafe dev-server port')
        if not name or len(name)>80:raise ValueError('Invalid service name')
        with self._lock:
            existing=self._services.get(name)
            if existing and existing['process'].poll() is None:
                raise RuntimeError('This service is already running')
        # Check before launching; strictPort is mandatory to handle the race.
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',port))==0:raise RuntimeError('Requested port already in use')
        binary,argv,cwd=self.runner.validate(spec)
        env=self.runner.child_env(spec.env)
        log_file=Path(log_file)
        log_file.parent.mkdir(parents=True,exist_ok=True)
        log=log_file.open('ab')
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
        try:
            proc=subprocess.Popen(argv,env=env,cwd=str(cwd) if cwd else None,
                                  stdout=log,stderr=subprocess.STDOUT,shell=False,creationflags=flags)
            try:job=_WindowsJob(proc)
            except Exception:proc.kill();proc.wait();raise
        finally:log.close()
        record={'process':proc,'job':job,'port':port,'log_file':str(log_file),'started':time.monotonic()}
        with self._lock:self._services[name]=record
        url=f'http://127.0.0.1:{port}/'
        until=time.monotonic()+wait_seconds
        while time.monotonic()<until:
            if cancel is not None and cancel.is_set():
                self.stop(name);raise InterruptedError('Dev server cancelled')
            if proc.poll() is not None:
                self.stop(name)
                raise RuntimeError(f'Dev server exited before readiness, code {proc.returncode}')
            try:
                with urllib.request.urlopen(url,timeout=.5) as response:
                    if response.status==200:
                        return {'status':'running','name':name,'pid':proc.pid,'port':port,'url':url,
                                'http_status':200,'log_file':str(log_file)}
            except (OSError,urllib.error.URLError):pass
            time.sleep(.2)
        self.stop(name)
        raise TimeoutError('Dev server failed HTTP 200 readiness check')

    def status(self,name:str)->dict:
        with self._lock:record=self._services.get(name)
        if not record:return {'status':'missing','name':name}
        proc=record['process']
        return {'status':'running' if proc.poll() is None else 'stopped','name':name,
                'pid':proc.pid,'port':record['port'],'log_file':record['log_file']}

    def list(self)->list[dict]:
        with self._lock:names=list(self._services)
        return [self.status(name) for name in names]

    def stop(self,name:str)->bool:
        with self._lock:record=self._services.pop(name,None)
        if not record:return False
        proc,job=record['process'],record['job']
        if proc.poll() is None:
            job.kill()
            if os.name!='nt':proc.terminate()
            try:proc.wait(timeout=4)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=4)
        job.close()
        return True

    def close(self):
        with self._lock:names=list(self._services)
        for name in names:self.stop(name)
