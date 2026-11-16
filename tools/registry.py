"""Read-only, explicitly allowlisted local tool adapters. Never shell=True."""
import asyncio, os, shutil, sys
from pathlib import Path
from core.security import child_env
import yaml
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]


def _test_python_executable():
    """Run pytest with the SAME interpreter as the active build/test environment.

    A frozen GUI executable is not a Python interpreter, so only use
    sys.executable for non-frozen Python processes.
    """
    if not getattr(sys, 'frozen', False) and Path(sys.executable).is_file():
        return sys.executable
    return shutil.which('python') or shutil.which('python3')
def project_python(root):
    root=Path(root)
    for folder in ('.barq-venv','.venv','venv'):
        for relative in ('Scripts/python.exe','bin/python'):
            candidate=root/folder/relative
            if candidate.is_file():return str(candidate)
    return _test_python_executable()

async def prepare_test_environment(workspace,confirmed=False):
    """Explicitly approved, project-scoped installation; never edit global Python."""
    if not confirmed:raise ValueError('Approval required for downloading test dependencies')
    from core.processes import background_options
    root=Path(workspace).resolve()
    if not root.is_dir():raise ValueError('Project directory missing')
    envdir=root/'.barq-venv'
    if envdir.is_symlink():raise ValueError('Environment directory must not be a symlink')
    python=_test_python_executable()
    if not python:raise ValueError('Install Python first')
    async def run(args):
        proc=await asyncio.create_subprocess_exec(*args,cwd=str(root),env=child_env(),
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,**background_options())
        try:out,err=await asyncio.wait_for(proc.communicate(),180)
        except (asyncio.TimeoutError,asyncio.CancelledError):
            proc.kill();await proc.communicate();raise
        return {'exit_code':proc.returncode,'stdout':out[-32000:].decode(errors='replace'),'stderr':err[-8000:].decode(errors='replace')}
    result=await run([python,'-m','venv',str(envdir)])
    if result['exit_code']:return result
    interpreter=envdir/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    return await run([str(interpreter),'-m','pip','install','--disable-pip-version-check','pytest>=8,<10'])

class Tool(BaseModel):
    id:str
    label:str
    type:str
    enabled:bool=False
    action:str|None=None
    executable_env:str|None=None
    arguments:list[str]=Field(default_factory=list)
    timeout_seconds:int=15

def load_tools(path=None):
    data=yaml.safe_load(Path(path or ROOT/'config/tools.yaml').read_text(encoding='utf-8'))
    return [Tool.model_validate(item) for item in data.get('tools',[])]

def status():
    out=[]
    for t in load_tools():
        available=bool(shutil.which('git')) if t.type=='git' else bool(shutil.which('gh')) if t.type=='gh' else bool(_test_python_executable()) if t.type=='test' else bool(t.executable_env and os.getenv(t.executable_env) and Path(os.environ[t.executable_env]).is_file())
        out.append({'id':t.id,'label':t.label,'type':t.type,'enabled':t.enabled,'available':available,'requires_confirmation':True})
    return out

async def execute(tool_id:str,workspace:str,confirmed:bool=False):
    if not confirmed:raise ValueError('Explicit confirmation is required for each tool invocation')
    tools={t.id:t for t in load_tools()}
    if tool_id not in tools:raise ValueError('Unknown tool')
    t=tools[tool_id]
    if not t.enabled:raise ValueError('Tool is disabled in config/tools.yaml')
    root=Path(workspace).expanduser().resolve()
    if not root.is_dir():raise ValueError('Workspace directory does not exist')
    if t.type=='git':
        if not shutil.which('git'):raise ValueError('git is not installed')
        if not (root/'.git').exists():raise ValueError('Workspace is not a Git repository')
        if t.action=='status':args=['git','-c','color.ui=false','status','--short','--branch']
        elif t.action=='log':args=['git','-c','color.ui=false','log','-8','--oneline']
        elif t.action=='diff':args=['git','-c','color.ui=false','diff','--no-ext-diff','--stat']
        else:raise ValueError('Unsupported Git action')
    elif t.type=='gh':
        if not shutil.which('gh'):raise ValueError('GitHub CLI (gh) is not installed')
        if t.action=='auth':args=['gh','auth','status']
        elif t.action=='prs':
            if not (root/'.git').exists():raise ValueError('Workspace is not a Git repository')
            args=['gh','pr','list','--limit','15','--json','number,title,state,url']
        else:raise ValueError('Unsupported GitHub action')
    elif t.type=='test':
        if t.action!='pytest':raise ValueError('Unsupported test runner')
        python=project_python(root)
        if not python:raise ValueError('Install Python and pytest on the Windows PC')
        if not any((root/item).exists() for item in ('tests','pytest.ini','pyproject.toml','setup.cfg')) and not any(root.glob('test_*.py')):
            raise ValueError('No Python test project found')
        args=[python,'-m','pytest','-q']
    elif t.type=='external':
        exe=os.getenv(t.executable_env or '')
        if not exe or not Path(exe).is_file():raise ValueError('External executable not configured')
        # No user-supplied command fragments or shell expansion.
        args=[exe,*t.arguments]
    else:raise ValueError('Unsupported tool adapter')
    proc=await asyncio.create_subprocess_exec(*args,cwd=str(root),env=child_env(),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
        creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0))
    try:out,err=await asyncio.wait_for(proc.communicate(),timeout=min(180,max(1,t.timeout_seconds)))
    except asyncio.TimeoutError:
        proc.kill();await proc.communicate();raise ValueError('Tool timed out')
    return {'tool':t.id,'exit_code':proc.returncode,'stdout':out[:32000].decode(errors='replace'),'stderr':err[:8000].decode(errors='replace')}
