"""Approved, bounded acceptance tests and noninteractive application startup."""
import asyncio,time,re
from contextlib import suppress
from core.security import child_env
from core.processes import background_options
from workspace.manager import checked_path
from tools.registry import project_python
from mission.tracking import load_project
from mission.blueprint import validate_blueprint

async def run_process(args,root,timeout):
    proc=await asyncio.create_subprocess_exec(*args,cwd=str(root),env=child_env(),
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,**background_options())
    async def drain(stream,limit):
        tail=bytearray()
        while chunk:=await stream.read(4096):
            tail.extend(chunk)
            if len(tail)>limit:del tail[:-limit]
        return tail.decode(errors='replace')
    stdout=asyncio.create_task(drain(proc.stdout,16000));stderr=asyncio.create_task(drain(proc.stderr,4000))
    try:
        await asyncio.wait_for(proc.wait(),timeout)
        out,err=await asyncio.wait_for(asyncio.gather(stdout,stderr),2)
        return {'exit_code':proc.returncode,'stdout':out,'stderr':err}
    except asyncio.CancelledError:
        if proc.returncode is None:
            with suppress(ProcessLookupError):proc.kill()
        await proc.wait()
        raise
    except asyncio.TimeoutError:
        if proc.returncode is None:
            with suppress(ProcessLookupError):proc.kill()
        await proc.wait()
        return {'exit_code':124,'stdout':'','stderr':'Application/test timeout; process stopped. Inspect startup or hanging tests.'}
    finally:
        for reader in (stdout,stderr):
            if not reader.done():reader.cancel()
        await asyncio.gather(stdout,stderr,return_exceptions=True)

async def verify_runtime(workspace,project,kind,confirmed=False):
    if not confirmed:raise ValueError('Explicit approval required to execute project code')
    mission=load_project(workspace,project)
    if not mission or not mission.get('blueprint'):raise ValueError('Approve a project plan first')
    plan=validate_blueprint(mission['blueprint'],mission['kind'])
    if mission['kind']!='desktop_python':raise ValueError('Automated runtime checks currently support Python projects only')
    root=checked_path(workspace,project);python=project_python(root)
    if not python:raise ValueError('Python interpreter unavailable')
    if kind=='smoke':
        entry=checked_path(workspace,project+'/main.py')
        result=await run_process([python,str(entry),'--barq-smoke-test'],root,20)
        if result['exit_code']==0 and 'BARQ_SMOKE_OK' not in result['stdout'].splitlines():
            result={**result,'exit_code':1,'stderr':result['stderr']+'\nMissing startup verification marker; implement the approved smoke-test contract.'}
        return {**result,'scope':'Noninteractive startup only; GUI usability is not verified'}
    if kind!='acceptance':raise ValueError('Unknown runtime check')
    checks={};deadline=time.monotonic()+180
    for requirement in plan['requirements']:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            return {'exit_code':124,'checks':checks,'stderr':'Acceptance check budget exhausted; unrun requirements are not passed'}
        for node in requirement['tests']:checked_path(workspace,project+'/'+node.split('::')[0])
        checks[requirement['id']]=await run_process([python,'-m','pytest','-q',*requirement['tests']],root,min(45,remaining))
        row=checks[requirement['id']]
        if row['exit_code']==0 and (not re.search(r'\b[1-9][0-9]* passed\b',row['stdout']) or re.search(r'\b[1-9][0-9]* (?:skipped|xfailed|xpassed|deselected)\b',row['stdout'])):
            row['exit_code']=1;row['stderr']+='\nNamed acceptance tests were not all executed successfully.'
        row['stdout']=row['stdout'][-350:];row['stderr']=row['stderr'][-250:]
        if row['exit_code']!=0:break
    passed=len(checks)==len(plan['requirements']) and all(r['exit_code']==0 for r in checks.values())
    return {'exit_code':0 if passed else 1,'checks':checks,
            'scope':'Only named tests linked by the approved plan; does not prove complete requirement coverage'}
