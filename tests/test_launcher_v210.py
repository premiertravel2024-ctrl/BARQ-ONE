"""Local launcher: deterministic parsing, fake-index results, policy, no network."""
import json,pytest,time
from pathlib import Path
from fastapi.testclient import TestClient
from launcher.nlu import parse,clean
from launcher.resolver import Resolver
from launcher.indexes import Index
from computer_control.safety.policy import Policy,Risk,Decision,Mode
from computer_control.adapters.base import FakeAdapter
from computer_control.executor.manager import Manager
from computer_control.audit.journal import Audit
from computer_control.tools.schema import validate

VERBS=['افتح','افتحلي','شغل','شغللي','وريني','هاتلي','open','launch','start','run','efta7','ممكن تشغل']
TARGETS=['كروم','يوتيوب','واتساب','فولدر التنزيلات','ملف التقرير','الحاسبة','اكسل','وورد','فايرفوكس','جيميل','الصور','Code','المستندات','Telegram','Google','التحميلات']
COMMANDS=[f'{v} {t}' for v in VERBS for t in TARGETS]

@pytest.mark.parametrize('command',COMMANDS)
def test_192_command_forms_parse(command):
    item=parse(command)
    assert item and item.verb=='open' and item.target_text

@pytest.mark.parametrize('text',['ينفع تفتح برامج؟','هو تقدر تشغل برامج؟','can you open apps?',
    'how to open Chrome?', 'ازاي افتح كروم؟','what is Chrome?',''] )
def test_capability_questions_do_not_execute(text):
    assert parse(text) is None

def test_egyptian_voice_alias_normalization():
    assert clean('يَا بَــرْق إفْتَحْلِي كرووووم').startswith('يا برق افتحلي')
    assert parse('يا برق افتحلي كروم').target_text=='كروم'
    assert parse('افتح ملف آخر ٢٠٢٦').target_text.endswith('2026')

def test_fuzzy_ambiguity_missing_and_no_network(tmp_path,monkeypatch):
    root=tmp_path/'documents';root.mkdir()
    f=root/'عرض.xlsx';f.write_bytes(b'not important');(root/'عرضه.xlsx').write_bytes(b'x')
    index=Index(tmp_path/'index.sqlite',[root]);index.reindex()
    apps=[]
    resolver=Resolver(index,Policy(allowed_folders=[str(root)]),app_source=lambda:apps)
    monkeypatch.setattr('socket.socket.connect',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Network prohibited')))
    result=resolver.resolve('افتح ملف عرض')
    assert result.decision=='choose'
    assert resolver.resolve('افتح ملف مش-موجود').decision=='not_found'
    assert resolver.resolve('ينفع تفتح برامج') is None

def test_launch_policy_extensions_and_uri(tmp_path):
    p=Policy(allowed_folders=[str(tmp_path)])
    for ext in ('.exe','.bat','.cmd','.ps1','.vbs','.msi','.msp','.js','.jse','.vbe','.wsf','.wsh','.hta','.scr','.com','.pif','.lnk','.jar','.reg','.dll','.cpl','.appx','.msix','.appinstaller','.py'):
        risk,decision,_=p.evaluate('open_file',{'path':str(tmp_path/('unsafe'+ext))})
        assert risk==Risk.HIGH and decision==Decision.ASK,ext
    assert p.evaluate('open_url',{'url':'javascript:alert(1)'})[1]==Decision.BLOCK
    assert p.evaluate('open_url',{'url':'ms-settings:privacy'})[1]==Decision.BLOCK
    assert p.evaluate('open_file',{'path':r'\\server\share\data.txt'})[1]==Decision.ASK
    assert p.evaluate('open_file',{'path':str(tmp_path/'.ssh/private.txt')})[1]==Decision.BLOCK
    assert p.evaluate('open_file',{'path':str(tmp_path/'safe.txt')})[1]==Decision.ALLOW


def test_direct_execution_approval_audit_and_stop(tmp_path):
    fake=FakeAdapter();a=Audit(tmp_path/'audit.jsonl')
    manager=Manager(fake,policy=Policy(enabled=True,mode=Mode.SMART,allowed_folders=[str(tmp_path)]),audit=a,planner=object())
    safe=tmp_path/'work.txt';safe.write_text('a')
    immediate=manager.launch_direct('open_file',{'path':str(safe)},'text')
    assert immediate['status']=='opened' and len(fake.calls)==1
    danger=tmp_path/'installer.msi';danger.write_text('not executable')
    pending=manager.launch_direct('open_file',{'path':str(danger)},'voice')
    assert pending['status']=='approval' and len(fake.calls)==1
    with pytest.raises(ValueError):manager.launch_direct('open_file',{'path':str(danger)},'voice','invalid','invalid')
    assert manager.launch_direct('open_file',{'path':str(danger)},'voice',pending['approval_id'],pending['approval_id'])['status']=='opened'
    assert len(fake.calls)==2
    assert 'launch_executed' in (tmp_path/'audit.jsonl').read_text()
    manager.tools.cancel()
    with pytest.raises(RuntimeError):manager.launch_direct('open_file',{'path':str(safe)})

def test_policy_cannot_be_bypassed_via_unknown_tool(tmp_path):
    manager=Manager(FakeAdapter(),policy=Policy(enabled=True),audit=Audit(tmp_path/'audit.jsonl'),planner=object())
    with pytest.raises(ValueError):manager.launch_direct('run_command',{'cmd':'echo hello'})


def test_resolver_no_execution_and_path_swap_detectable(tmp_path, monkeypatch):
    """A selected file that disappears must fail closed without OS symlink privileges.

    This used to call Path.symlink_to(), which raises WinError 1314 on ordinary
    Windows user accounts. Renaming the file exercises the real missing-path
    check and the launcher execution boundary without needing elevation.
    """
    from fastapi import HTTPException
    import launcher.api as launcher_api

    root=tmp_path/'work';root.mkdir();target=root/'myfile.txt';target.write_text('original')
    idx=Index(tmp_path/'index.sqlite',[root]);idx.reindex()
    fake=FakeAdapter()
    r=Resolver(idx,Policy(allowed_folders=[str(root)]),app_source=lambda:[])
    item=r.resolve('افتح ملف myfile')
    assert item.candidates and item.decision=='auto'
    assert fake.calls==[]
    entry=r.candidate(item.candidates[0]['id'])
    assert entry.realpath==str(target.resolve())

    target.rename(root/'changed.txt')
    with pytest.raises(FileNotFoundError):
        target.resolve(strict=True)
    monkeypatch.setattr(launcher_api,'resolver',lambda:r)
    monkeypatch.setattr(launcher_api,'launcher_settings',lambda:{'enabled':True,'files':True})
    with pytest.raises(HTTPException) as err:
        launcher_api._launch(entry.id)
    assert err.value.status_code==409
    assert fake.calls==[]


def test_launcher_rejects_canonical_path_swap_without_symlink_privileges(tmp_path,monkeypatch):
    """Simulate a symlink-redirection race without creating a Windows symlink.

    The production path-canonicalization and denial branch still execute.
    """
    from fastapi import HTTPException
    import launcher.api as launcher_api

    root=tmp_path/'work';root.mkdir()
    original=root/'myfile.txt';original.write_text('original')
    redirected=root/'changed.txt';redirected.write_text('changed')
    idx=Index(tmp_path/'index.sqlite',[root]);idx.reindex()
    r=Resolver(idx,Policy(allowed_folders=[str(root)]),app_source=lambda:[])
    item=r.resolve('افتح ملف myfile')
    assert item.candidates and item.decision=='auto'
    entry=r.candidate(item.candidates[0]['id'])
    assert entry.realpath==str(original.resolve())
    monkeypatch.setattr(launcher_api,'resolver',lambda:r)
    monkeypatch.setattr(launcher_api,'launcher_settings',lambda:{'enabled':True,'files':True})
    # Only the final path-resolution result is simulated: no elevated rights.
    class RedirectedPath:
        def __init__(self,path):
            assert path==str(original)
        def resolve(self,strict=False):
            return redirected.resolve(strict=strict)
    monkeypatch.setattr(launcher_api,'Path',RedirectedPath)
    with pytest.raises(HTTPException) as err:
        launcher_api._launch(entry.id)
    assert err.value.status_code==409


def test_expired_launcher_candidate_returns_410_not_attribute_error(tmp_path,monkeypatch):
    """An unknown candidate ID must not produce a server-side 500."""
    from fastapi import HTTPException
    import launcher.api as launcher_api
    r=Resolver(Index(tmp_path/'index.sqlite',[]),Policy(),app_source=lambda:[])
    monkeypatch.setattr(launcher_api,'resolver',lambda:r)
    monkeypatch.setattr(launcher_api,'launcher_settings',lambda:{'enabled':True,'files':True})
    with pytest.raises(HTTPException) as err:
        launcher_api._launch('0'*32)
    assert err.value.status_code==410


def test_api_routes_no_cloud(monkeypatch):
    from api import app
    c=TestClient(app)
    assert c.post('/v1/launch/resolve',json={'text':'ينفع تفتح برامج؟'}).json()['decision']=='not_command'
    assert c.post('/v1/launch/resolve',json={'text':'افتح يوتيوب'}).json()['decision']=='auto'
    assert c.get('/v1/launch/settings').status_code==200
    assert c.get('/v1/launch/status').status_code==200

VOICE_TRANSCRIPTS=COMMANDS[:100]
@pytest.mark.parametrize('phrase',VOICE_TRANSCRIPTS)
def test_voice_transcripts_are_resolved_without_llm(phrase,monkeypatch):
    from launcher.api import router
    from launcher.nlu import parse
    assert parse(phrase) is not None
    # A deterministic transcript is enough to trigger the resolver, no model needed.

@pytest.mark.parametrize('text',['افتح ملف installer.msi','افتح واتساب ويب','شغل واتساب','افتح فولدر سطح المكتب'])
def test_voice_and_text_share_one_parser(text):
    assert parse(text)==parse(text)
