"""Deliberately reviewed Git/GitHub write operations. No shell strings or auto push."""
from core.processes import background_options
import asyncio,re,uuid,time,shutil
from pathlib import Path
from workspace.manager import root_of,checked_path
from core.security import child_env

PENDING={}

class GitActionError(ValueError):pass

async def call(args,root,timeout=35):
    exe=shutil.which(args[0]);
    if not exe:raise GitActionError(f'{args[0]} is missing; install Git / GitHub CLI')
    p=await asyncio.create_subprocess_exec(exe,*args[1:],cwd=str(root),env=child_env(),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,**background_options())
    try:out,err=await asyncio.wait_for(p.communicate(),timeout=timeout)
    except asyncio.TimeoutError:p.kill();await p.wait();raise GitActionError('Git operation timed out')
    result={'exit_code':p.returncode,'stdout':out.decode(errors='replace')[:20000],'stderr':err.decode(errors='replace')[:2000]}
    if p.returncode:raise GitActionError((result['stderr'] or result['stdout'])[:900])
    return result

def _branch(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,100}',name) or name.startswith(('.','-')) or '..' in name or name.endswith(('/','.')):
        raise GitActionError('Invalid branch name')

def _repo(workspace):
    root=root_of(workspace)
    if not (root/'.git').exists():raise GitActionError('Open the root of a local Git repository')
    return root

async def preview(workspace,action,params):
    root=_repo(workspace)
    if action=='commit':
        files=params.get('files',[]);message=str(params.get('message','')).strip()
        if not isinstance(files,list) or len(files)<1 or len(files)>30 or len(message)<3 or len(message)>180:raise GitActionError('Select 1–30 files and a commit message')
        paths=[]
        for path in files:
            if not isinstance(path,str):raise GitActionError('Invalid path')
            f=checked_path(workspace,path)
            if not f.exists():raise GitActionError('Commit file not found')
            paths.append(path)
        evidence=await call(['git','diff','--','*'],root) if False else await call(['git','status','--short','--',*paths],root)
        summary='Commit only selected files:\n'+evidence['stdout']+'\nMessage: '+message
        cmd=['git','commit','--only','-m',message,'--',*paths]
    elif action=='branch':
        name=str(params.get('name',''));_branch(name)
        summary='Create new branch '+name+' (will switch HEAD to it)'
        cmd=['git','checkout','-b',name]
    elif action=='push':
        branch=str(params.get('branch',''));_branch(branch)
        summary='PUSH branch '+branch+' to origin (this publishes local commits to remote repository)'
        cmd=['git','push','--set-upstream','origin',branch]
    elif action=='pr':
        title=str(params.get('title','')).strip();body=str(params.get('body','')).strip()
        base=str(params.get('base','main'));_branch(base)
        if not (3<=len(title)<=150 and len(body)<=8000):raise GitActionError('Invalid PR title or body')
        summary='Create GitHub pull request targeting '+base+' titled '+title
        cmd=['gh','pr','create','--base',base,'--title',title,'--body',body]
    else:raise GitActionError('Unsupported GitHub action')
    token=uuid.uuid4().hex
    PENDING[token]={'cmd':cmd,'workspace':str(root),'expires':time.monotonic()+600,'action':action}
    return {'approval_id':token,'action':action,'command_preview':cmd,'summary':summary,'expires_in_seconds':600}

async def apply(approval_id,confirmed=False):
    if not confirmed:raise GitActionError('Explicit approval required')
    job=PENDING.pop(approval_id,None)
    if not job or time.monotonic()>job['expires']:raise GitActionError('Git approval expired')
    result=await call(job['cmd'],job['workspace'],timeout=80)
    return {'action':job['action'],**result}
