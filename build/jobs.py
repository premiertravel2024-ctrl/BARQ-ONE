"""Approved build profiles, bounded logs, and real process exit verification."""
from pathlib import Path
import asyncio, os, re, shutil, sys, tempfile, time, uuid
from core.security import child_env
from core.tool_locator import find_tool
from workspace.manager import root_of, checked_path

JOBS={}
MAX_JOBS=80

class BuildError(ValueError):pass

def profiles(workspace):
    root=root_of(workspace)
    return [{'id':'python','label':'Python → Windows EXE (PyInstaller)','ready':sys.platform=='win32' and bool(shutil.which('pyinstaller') or shutil.which('python'))},
            {'id':'tauri','label':'Tauri 2 → Windows Installer','ready':sys.platform=='win32' and bool(find_tool('npm')) and (root/'src-tauri/tauri.conf.json').exists()},
            {'id':'electron','label':'Electron → Windows Installer','ready':sys.platform=='win32' and bool(find_tool('npm')) and (root/'package.json').exists()}]

def preview(workspace,profile,entry='',name='Application'):
    root=root_of(workspace)
    if sys.platform!='win32':raise BuildError('Building Windows EXE requires Windows. Run the app on your Windows PC or use the Windows CI workflow.')
    if len(name)>60 or not re.fullmatch(r'[a-zA-Z][\w -]{0,59}',name):raise BuildError('Invalid output name')
    if profile=='python':
        path=checked_path(workspace,entry)
        if path.suffix.lower()!='.py' or not path.is_file():raise BuildError('Select an existing Python entry script')
        python=sys.executable if not getattr(sys,'frozen',False) else (find_tool('python') or 'python')
        cmd=[python,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--name',name,str(path.relative_to(root))]
    elif profile=='tauri':
        if not (root/'src-tauri/tauri.conf.json').exists():raise BuildError('Tauri project not found')
        cmd=[find_tool('npm') or 'npm','run','tauri','build']
    elif profile=='electron':
        package=root/'package.json'
        if not package.exists():raise BuildError('package.json not found')
        import json
        scripts=json.loads(package.read_text(encoding='utf-8')).get('scripts',{})
        if 'dist' not in scripts:raise BuildError('package.json must define a reviewed dist script')
        cmd=[find_tool('npm') or 'npm','run','dist']
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

async def _setup_python(command, log):
    from api_routes.openhub_tools import ensure_build_tool, network_allowed, read_auto_tools
    from core.processes import background_options
    from core.paths import data_dir

    python = command[0]
    if python == 'python':
        python = await asyncio.to_thread(ensure_build_tool, 'python', 'python/cpython')
        if not python:
            raise BuildError('Python is unavailable. Install it from OpenHub or enable automatic build tools.')
        command[0] = python

    async def run(args, timeout):
        proc = await asyncio.create_subprocess_exec(*args, env=child_env(), stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT, **background_options())
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            raise
        return proc.returncode, output

    status, _ = await run([python, '-I', '-m', 'PyInstaller', '--version'], 30)
    if status == 0:
        return None
    if not read_auto_tools()['enabled'] or not network_allowed():
        raise BuildError('PyInstaller is unavailable. Enable automatic build tools or install PyInstaller in the build interpreter.')
    log('Preparing PyInstaller in a temporary BARQ build environment…')
    env = tempfile.TemporaryDirectory(prefix='barq-python-build-', dir=data_dir())
    try:
        status, output = await run([python, '-I', '-m', 'venv', env.name], 90)
        if status != 0:
            raise BuildError('Could not create the Python build environment: '+output.decode(errors='replace')[-400:])
        interpreter = str(Path(env.name) / 'Scripts' / 'python.exe')
        version = 'pyinstaller==6.22.3'
        status, output = await run([interpreter, '-m', 'pip', '--isolated', 'install', '--index-url',
                                    'https://pypi.org/simple', '--only-binary=:all:', version], 240)
        if status != 0:
            raise BuildError('Could not prepare PyInstaller: '+output.decode(errors='replace')[-400:])
        command[0] = interpreter
        return env
    except BaseException:
        await asyncio.to_thread(env.cleanup)
        raise


async def _execute(j):
    temporary_env = None
    try:
        root=Path(j['workspace'])
        if j['profile'] in {'tauri','electron'} and j['command'][0] == 'npm':
            from api_routes.openhub_tools import ensure_build_tool
            j['log'] += '\nChecking Node.js/npm in OpenHub…\n'
            npm = await asyncio.to_thread(ensure_build_tool, 'npm', 'nodejs/node')
            if not npm:
                raise BuildError('Node.js/npm is unavailable. Install it from OpenHub or enable automatic build tools.')
            j['command'][0] = npm
        if j['profile'] == 'python':
            def log(message):
                j['log'] += '\n' + message
            temporary_env = await _setup_python(j['command'], log)
        elif Path(j['command'][0]).suffix.lower() == '.cmd':
            npm_root = Path(j['command'][0]).parent
            cli = npm_root / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js'
            node = npm_root / 'node.exe'
            if node.is_file() and cli.is_file():
                j['command'] = [str(node), str(cli), *j['command'][1:]]
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
    finally:
        if temporary_env:
            await asyncio.to_thread(temporary_env.cleanup)


async def build_approved(workspace,profile,entry,name):
    """Agent's already approved build action uses the same validated profiles as Studio."""
    job=preview(workspace,profile,entry,name)
    await run_job(job['id'],True)
    await JOBS[job['id']]['task']
    result=public(job['id'])
    return {'exit_code':0 if result['status']=='success' else (result['exit_code'] or 1),
            'status':result['status'],'artifacts':result['artifacts'],'log':result['log'][-24000:]}
