"""Approved build profiles, bounded logs, and real process exit verification."""
from pathlib import Path
import asyncio, os, re, shutil, sys, time, uuid
from core.security import child_env
from workspace.manager import root_of, checked_path

JOBS={}
MAX_JOBS=80

class BuildError(ValueError):pass

def profiles(workspace):
    root=root_of(workspace)
    return [{'id':'python','label':'Python → Windows EXE (PyInstaller)','ready':sys.platform=='win32' and bool(shutil.which('pyinstaller') or shutil.which('python'))},
            {'id':'tauri','label':'Tauri 2 → Windows Installer','ready':sys.platform=='win32' and bool(shutil.which('npm')) and (root/'src-tauri/tauri.conf.json').exists()},
            {'id':'electron','label':'Electron → Windows Installer','ready':sys.platform=='win32' and bool(shutil.which('npm')) and (root/'package.json').exists()}]

def preview(workspace,profile,entry='',name='Application'):
    root=root_of(workspace)
    if sys.platform!='win32':raise BuildError('Building Windows EXE requires Windows. Run the app on your Windows PC or use the Windows CI workflow.')
    if len(name)>60 or not re.fullmatch(r'[a-zA-Z][\w -]{0,59}',name):raise BuildError('Invalid output name')
    if profile=='python':
        path=checked_path(workspace,entry)
        if path.suffix.lower()!='.py' or not path.is_file():raise BuildError('Select an existing Python entry script')
        python=sys.executable if not getattr(sys,'frozen',False) else (shutil.which('python') or shutil.which('py'))
        if not python:raise BuildError('Install Python and PyInstaller to build Python projects')
        cmd=[python,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name',name,str(path.relative_to(root))]
    elif profile=='tauri':
        if not (root/'src-tauri/tauri.conf.json').exists():raise BuildError('Tauri project not found')
        if not shutil.which('npm'):raise BuildError('npm is missing')
        cmd=['npm','run','tauri','build']
    elif profile=='electron':
        package=root/'package.json'
        if not package.exists():raise BuildError('package.json not found')
        import json
        scripts=json.loads(package.read_text(encoding='utf-8')).get('scripts',{})
        if 'dist' not in scripts:raise BuildError('package.json must define a reviewed dist script')
        if not shutil.which('npm'):raise BuildError('npm is missing')
        cmd=['npm','run','dist']
    else:raise BuildError('Unknown build profile')
    token=uuid.uuid4().hex
    JOBS[token]={'id':token,'workspace':str(root),'profile':profile,'name':name,'command':cmd,'status':'awaiting_approval','log':'','created':time.time(),'exit_code':None,'artifacts':[]}
    return public(token)

def public(id):
    j=JOBS.get(id)
    if not j:raise BuildError('Unknown build job')
    return {k:v for k,v in j.items() if k not in ('task','_process')}

async def run_job(id,confirmed=False):
    if not confirmed:raise BuildError('Explicit approval required')
    j=JOBS.get(id)
    if not j:raise BuildError('Unknown build job')
    if j['status']!='awaiting_approval':raise BuildError('Build already started')
    j['status']='running';j['task']=asyncio.create_task(_execute(j))
    return public(id)

async def _execute(j):
    try:
        root=Path(j['workspace'])
        def artifacts():
            files=[]
            for directory in (root/'dist',root/'src-tauri'/'target'/'release'/'bundle'):
                if directory.is_dir() and not directory.is_symlink():
                    files.extend(x for x in directory.rglob('*') if x.is_file() and not x.is_symlink()
                                 and x.resolve().is_relative_to(root) and x.suffix.lower() in ('.exe','.msi','.zip'))
            return files
        previous={str(x):(x.stat().st_mtime_ns,x.stat().st_size) for x in artifacts()}
        p=await asyncio.create_subprocess_exec(*j['command'],cwd=j['workspace'],env=child_env(),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,
            creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0))
        j['_process']=p
        async def capture():
            while True:
                data=await p.stdout.read(4096)
                if not data:break
                j['log']=(j['log']+data.decode(errors='replace'))[-100000:]
            await p.wait()
        try:await asyncio.wait_for(capture(),timeout=900)
        except asyncio.TimeoutError:
            p.kill();await p.wait();j['status']='timeout';j['exit_code']=-1;return
        j['exit_code']=p.returncode;j['status']='success' if p.returncode==0 else 'failed'
        if j['status']=='success':
            j['artifacts']=[str(x.relative_to(root)) for x in artifacts()
                if x.stat().st_size>0 and previous.get(str(x))!=(x.stat().st_mtime_ns,x.stat().st_size)][:30]
            if not j['artifacts']:
                j['status']='failed';j['log']+='\nBuild exited successfully but produced no fresh executable or installer.'
    except asyncio.CancelledError:
        process=j.get('_process')
        if process is not None and process.returncode is None:
            process.kill();await process.wait()
        j['status']='stopped';j['exit_code']=-1
    except Exception as exc:
        j['status']='failed';j['log']+='\n'+str(exc)[:500]


async def build_approved(workspace,profile,entry,name):
    """Agent's already approved build action uses the same validated profiles as Studio."""
    job=preview(workspace,profile,entry,name)
    await run_job(job['id'],True)
    await JOBS[job['id']]['task']
    result=public(job['id'])
    return {'exit_code':0 if result['status']=='success' else (result['exit_code'] or 1),
            'status':result['status'],'artifacts':result['artifacts'],'log':result['log'][-24000:]}
