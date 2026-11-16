"""Negative controls for v2.31 execution layer; all tests use fakes/temp dirs."""
import hashlib,json,os,sys,threading,time
from pathlib import Path
import pytest
from execution.runner import Command,Runner,CommandRejected
from execution.grants import GrantStore
from execution.recipes import scaffold_react
from execution.service import ExecutionService
from computer_control.state_store import TaskStateStore
from computer_control.safety.policy import Policy,Decision

def test_runner_rejects_unlisted_program():
    with pytest.raises(CommandRejected):Runner.resolve('cmd')
    with pytest.raises(CommandRejected):Runner.resolve('curl')

@pytest.mark.parametrize('arg',['hello&whoami','test|powershell','foo>bad','%PATH%','!VAR!','quote"',
                                 'x\ny','x\x00z','^exfil','safe<unsafe'])
def test_cmd_shim_blocks_meta(monkeypatch,arg):
    monkeypatch.setattr(Runner,'resolve',staticmethod(lambda p: r'C:\Windows\nodejs\npm.cmd'))
    with pytest.raises(CommandRejected):Runner.validate(Command('npm',(arg,)))

def test_runner_uses_argv_without_shell(monkeypatch,tmp_path):
    monkeypatch.setattr(Runner,'resolve',staticmethod(lambda _:sys.executable))
    res=Runner().run(Command('python',('-c','print("اهلا من برق")'),cwd=str(tmp_path)))
    assert res.returncode==0 and 'اهلا من برق' in res.stdout and not res.timed_out

def test_runner_environment_secrets_removed(monkeypatch):
    monkeypatch.setenv('PRIVATE_API_KEY','NO')
    monkeypatch.setenv('REPO_TOKEN','HIDE')
    env=Runner.child_env({'BARQ_TASK':'visible'})
    assert 'PRIVATE_API_KEY' not in env and 'REPO_TOKEN' not in env
    assert env['BARQ_TASK']=='visible'
    with pytest.raises(CommandRejected):Runner.child_env({'USER_SECRET':'bad'})

def test_runner_timeout(monkeypatch,tmp_path):
    monkeypatch.setattr(Runner,'resolve',staticmethod(lambda _:sys.executable))
    res=Runner().run(Command('python',('-c','import time;time.sleep(1)'),cwd=str(tmp_path),timeout_total=.25,timeout_idle=.25))
    assert res.timed_out

def test_runner_cancel(monkeypatch,tmp_path):
    monkeypatch.setattr(Runner,'resolve',staticmethod(lambda _:sys.executable))
    cancel=threading.Event();cancel.set()
    res=Runner().run(Command('python',('-c','import time;time.sleep(1)'),cwd=str(tmp_path)),cancel=cancel)
    assert res.cancelled

def test_grant_scopes_and_revocation(tmp_path):
    folder=tmp_path/'project';folder.mkdir()
    store=GrantStore(tmp_path/'grants.json')
    with pytest.raises(ValueError):store.grant(str(folder),['system_admin'])
    grant=store.grant(str(folder),['read','create','write'])
    assert store.permits(str(folder/'foo'/'file.txt'),'write')
    assert not store.permits(str(folder/'foo'/'file.txt'),'build')
    assert not store.permits(str(tmp_path/'outside.txt'),'write')
    assert not store.permits(str(folder/'..'/'outside.txt'),'write')
    assert not store.permits(str(folder/'.ssh'/'key'),'read')
    assert store.revoke(grant.id)
    assert not store.permits(str(folder/'file'),'write')

def test_grant_does_not_approve_blocked_actions(tmp_path,monkeypatch):
    import execution.grants
    folder=tmp_path/'project';folder.mkdir()
    store=GrantStore(tmp_path/'grants.json')
    store.grant(str(folder),['read','write','create'])
    monkeypatch.setattr(execution.grants,'GrantStore',lambda:store)
    policy=Policy(enabled=True,allowed_folders=[])
    assert policy.evaluate('write_file',{'path':str(folder/'file.txt'),'text':'x'})[1]==Decision.ALLOW
    assert policy.evaluate('write_file',{'path':str(tmp_path/'outside'),'text':'x'})[1]==Decision.ASK
    assert policy.evaluate('read_file',{'path':str(folder/'.env')})[1]==Decision.BLOCK
    assert policy.evaluate('delete',{'path':str(folder/'file.txt'),'permanent':True})[1]==Decision.BLOCK


def test_recipe_requires_grant_and_verifies(tmp_path):
    root=tmp_path/'projects';root.mkdir();store=GrantStore(tmp_path/'g.json')
    with pytest.raises(PermissionError):scaffold_react(root,store)
    store.grant(str(root),['create','write'])
    result=scaffold_react(root,store)
    assert result['status']=='verified' and result['file_count']>=5
    assert (root/'barq-react-app'/'src'/'main.tsx').exists()
    with pytest.raises(FileExistsError):scaffold_react(root,store)


def test_no_voice_approval_or_permission_escalation():
    class M:
        def __init__(self):self.requests=[]
        def start(self,goal,model='auto',source='text'):
            self.requests.append((goal,model,source));return {'id':'1'}
        def approve(self,*args):raise AssertionError('Voice must not approve')
    m=M();svc=ExecutionService(m)
    assert svc.submit('افتح برنامج',source='voice')['id']=='1'
    assert svc.submit('افتح برنامج',source='chat')['id']=='1'
    assert m.requests==[('افتح برنامج','auto','voice'),('افتح برنامج','auto','text')]
    with pytest.raises(ValueError):svc.submit('test',source='unknown')


def test_step_ledger_privacy_no_committing_without_proof(tmp_path):
    db=TaskStateStore(tmp_path/'tasks.sqlite3')
    digest=hashlib.sha256(b'secret input').hexdigest()
    db.step_started('t','create','create_dir',digest,'a')
    with pytest.raises(ValueError):db.step_finished('t','create','committed','unverified')
    db.step_finished('t','create','committed','verified')
    with pytest.raises(ValueError):db.step_started('t','create','create_dir',digest,'a')
    assert db.steps('t')[0]['status']=='committed'
    assert 'secret input' not in (tmp_path/'tasks.sqlite3').read_bytes().decode('utf-8','ignore')
