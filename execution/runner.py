"""Structured child-process runner for Windows automation.

Never calls a command shell and never accepts a model-authored command string.
Callers must enforce BARQ's independent consent/risk policy BEFORE invoking it.
"""
from __future__ import annotations
import dataclasses
import os
import queue
import re
from core.security import is_secret_env_name
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Mapping

_ALLOWED = frozenset({'git','gh','node','npm','npx','pnpm','yarn','python','py',
                      'pip','code','powershell','pwsh','winget','explorer'})
_WINDOWS_SHIM = frozenset({'npm','npx','pnpm','yarn','code'})
_FORBIDDEN_CMD = re.compile(r'[&|<>^%!"\r\n\x00-\x1f]')
MAX_CAPTURE = 102_400

class CommandRejected(ValueError):
    pass

@dataclasses.dataclass(frozen=True)
class Command:
    program: str
    args: tuple[str, ...] = ()
    cwd: str | None = None
    timeout_total: float = 1200.0
    timeout_idle: float = 600.0
    output_cap: int = MAX_CAPTURE
    env: Mapping[str, str] | None = None

@dataclasses.dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False

class _WindowsJob:
    """Kernel Job Object with kill-on-close; attach before the process runs."""
    def __init__(self, process: subprocess.Popen):
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.AssignProcessToJobObject.restype = wintypes.BOOL
        k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k.TerminateJobObject.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        handle = k.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'CreateJobObjectW failed')
        self._k = k
        # Set JOBOBJECT_EXTENDED_LIMIT_INFORMATION.LimitFlags = KILL_ON_JOB_CLOSE.
        # Offset 16 in JOBOBJECT_BASIC_LIMIT_INFORMATION (platforms x86/x64).
        class BasicLimit(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),
                        ('LimitFlags',wintypes.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),
                        ('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',wintypes.DWORD),
                        ('Affinity',ctypes.c_size_t),('PriorityClass',wintypes.DWORD),
                        ('SchedulingClass',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [('ReadOperationCount',ctypes.c_ulonglong),('WriteOperationCount',ctypes.c_ulonglong),
                        ('OtherOperationCount',ctypes.c_ulonglong),('ReadTransferCount',ctypes.c_ulonglong),
                        ('WriteTransferCount',ctypes.c_ulonglong),('OtherTransferCount',ctypes.c_ulonglong)]
        class Extended(ctypes.Structure):
            _fields_ = [('BasicLimitInformation',BasicLimit),('IoInfo',IO),
                        ('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),
                        ('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
        info=Extended()
        info.BasicLimitInformation.LimitFlags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        if not k.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            err=ctypes.get_last_error();k.CloseHandle(handle)
            raise OSError(err,'SetInformationJobObject failed')
        if not k.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle))):
            err=ctypes.get_last_error();k.CloseHandle(handle)
            raise OSError(err,'AssignProcessToJobObject failed')
        self.handle=handle
    def kill(self):
        if self.handle is not None:
            self._k.TerminateJobObject(self.handle,1)
    def close(self):
        if self.handle is not None:
            self._k.CloseHandle(self.handle)
            self.handle=None

class Runner:
    def __init__(self, on_line: Callable[[str,str],None] | None = None):
        self.on_line=on_line

    @staticmethod
    def resolve(program: str) -> str:
        base=Path(program).name.lower()
        base=re.sub(r'\.(?:exe|cmd|bat)$','',base)
        if base not in _ALLOWED:
            raise CommandRejected('Program not on the vetted BARQ tool list')
        # An absolute path named git.exe under Downloads is NOT trusted merely
        # because its basename is 'git'. It must resolve to the PATH entry
        # for that vetted program (or a fixed known-install location).
        requested=base
        found=shutil.which(requested)
        if found is None and os.name=='nt':
            from core.tool_locator import find_tool
            found=find_tool(requested)
        if found is None and os.name=='nt':
            candidates=[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/cmd/git.exe',
                        Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Microsoft VS Code/bin/code.cmd']
            found=next((str(path) for path in candidates if path.stem.lower()==base and path.is_file()),None)
        if not found:
            raise CommandRejected(f'{base} is not installed or is not on PATH')
        found=str(Path(found).resolve())
        if os.path.isabs(program) and Path(found)!=Path(program).resolve():
            raise CommandRejected('Program path must resolve to the approved installed binary')
        if Path(found).suffix.lower() in ('.bat','.cmd') and base not in _WINDOWS_SHIM:
            raise CommandRejected('Unexpected Windows command shim')
        return found

    @classmethod
    def validate(cls, spec:Command) -> tuple[str,list[str],Path|None]:
        binary=cls.resolve(spec.program)
        if not isinstance(spec.args,tuple) or any(not isinstance(arg,str) for arg in spec.args):
            raise CommandRejected('Command arguments must be a string tuple')
        if sum(len(x) for x in spec.args)>15_000:
            raise CommandRejected('Command arguments too long')
        if any('\x00' in x or '\r' in x or '\n' in x for x in spec.args):
            raise CommandRejected('Control characters are not allowed in program arguments')
        if Path(binary).suffix.lower() in ('.bat','.cmd') and any(_FORBIDDEN_CMD.search(x) for x in spec.args):
            raise CommandRejected('Windows .cmd metacharacters rejected')
        if not 0 < spec.timeout_total <= 7200 or not 0 < spec.timeout_idle <= 1800:
            raise CommandRejected('Invalid timeout')
        if not 128 <= spec.output_cap <= 1_000_000:
            raise CommandRejected('Invalid output limit')
        cwd=Path(spec.cwd).resolve(strict=True) if spec.cwd else None
        if cwd is not None and not cwd.is_dir():
            raise CommandRejected('Working directory is not a folder')
        return binary,[binary,*spec.args],cwd

    @staticmethod
    def child_env(additions: Mapping[str,str]|None=None)->dict[str,str]:
        result={k:v for k,v in os.environ.items() if not is_secret_env_name(k)}
        for key,val in (additions or {}).items():
            if not isinstance(key,str) or not isinstance(val,str) or '\x00' in key+val:
                raise CommandRejected('Invalid environment setting')
            if is_secret_env_name(key):
                raise CommandRejected('Secrets may not be injected into child environment')
            result[key]=val
        return result

    def run(self,spec:Command,*,cancel:threading.Event|None=None,log_file:Path|None=None)->CommandResult:
        binary,argv,cwd=self.validate(spec)
        env=self.child_env(spec.env)
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
        started=time.monotonic()
        process=subprocess.Popen(argv,cwd=str(cwd) if cwd else None,env=env,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,bufsize=0,
            shell=False,creationflags=creationflags)
        try:job=_WindowsJob(process)
        except Exception:
            process.kill();process.wait(timeout=5)
            raise
        q:queue.Queue[tuple[str,bytes|None]]=queue.Queue()
        def pump(name,pipe):
            try:
                while True:
                    chunk=pipe.readline()
                    if not chunk:break
                    q.put((name,chunk))
            finally:q.put((name,None))
        threads=[threading.Thread(target=pump,args=(name,pipe),daemon=True)
                 for name,pipe in (('stdout',process.stdout),('stderr',process.stderr))]
        for thread in threads:thread.start()
        output={'stdout':bytearray(),'stderr':bytearray()}
        truncated=False;finished=0;last=started;timed_out=False;cancelled=False
        file=None;logged=0
        try:
            if log_file:
                log_file=Path(log_file);log_file.parent.mkdir(parents=True,exist_ok=True)
                file=log_file.open('ab')
            while finished<2 or process.poll() is None:
                now=time.monotonic()
                if cancel and cancel.is_set():
                    cancelled=True;job.kill()
                    if process.poll() is None:process.kill()
                    break
                if now-started>spec.timeout_total or now-last>spec.timeout_idle:
                    timed_out=True;job.kill()
                    if process.poll() is None:process.kill()
                    break
                try:name,line=q.get(timeout=.1)
                except queue.Empty:continue
                if line is None:
                    finished+=1;continue
                last=time.monotonic()
                remaining=max(0,spec.output_cap-len(output[name]))
                output[name].extend(line[:remaining]);truncated|=len(line)>remaining
                if file and logged < 1_048_576:
                    # Bound on-disk logs too; process output is untrusted.
                    from computer_control.safety.policy import redact
                    safe_line=redact(line.decode('utf-8','replace')).encode('utf-8')
                    part=safe_line[:max(0,min(8192,1_048_576-logged))]
                    file.write(part);file.flush();logged+=len(part)
                if self.on_line:
                    from computer_control.safety.policy import redact
                    self.on_line(name,redact(line.decode('utf-8','replace')[:4000]))
            if timed_out or cancelled:
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill()
            rc=process.wait(timeout=10)
        finally:
            if file:file.close()
            job.close()
            if process.stdout:process.stdout.close()
            if process.stderr:process.stderr.close()
        return CommandResult(Path(binary).name,rc,
            output['stdout'].decode('utf-8','replace'),output['stderr'].decode('utf-8','replace'),
            round(time.monotonic()-started,3),timed_out,cancelled,truncated)
