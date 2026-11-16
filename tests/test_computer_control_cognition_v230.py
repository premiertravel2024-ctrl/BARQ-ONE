"""v2.30 gated desktop intent / evidence / completion regression tests.

Cross-platform: no access to user's desktop, voice input or real Windows apps.
"""
import asyncio
from pathlib import Path
import pytest
from computer_control.cognition import interpret_goal, verify_action, verify_goal
from computer_control.safety.policy import Policy,Decision,Mode
from computer_control.tools.schema import validate
from computer_control.adapters.base import FakeAdapter,Perception
from computer_control.executor.manager import Manager
from computer_control.audit.journal import Audit


def test_egyptian_voice_phrases_identified_without_exec():
    it=interpret_goal('افتح المفكرة','voice')
    assert it.label=='open_app' and it.source=='voice' and not it.compound
    assert interpret_goal('افتح المفكرة وبعدين اكتب سطر','voice').compound
    assert interpret_goal('وريني البرامج المفتوحة').label=='inspect'
    with pytest.raises(ValueError):interpret_goal('افتح','microphone_secret')


def test_goal_intent_cannot_mistake_delete_for_create():
    it=interpret_goal('انشئ مجلد')
    assert it.label=='file_operation' and it.expected_tool=='create_dir'
    wrong=verify_goal(it,[{'tool':'delete','status':'ok','verification':'verified'}])
    assert wrong.status=='unverified'
    right=verify_goal(it,[{'tool':'create_dir','status':'ok','verification':'verified'}])
    assert right.status=='verified'


def test_visual_changed_not_verified_goal():
    before={'window':'A','elements':[],'screenshot_hash':'old'}
    after={'window':'B','elements':[],'screenshot_hash':'new'}
    proof=verify_action('click',{'x':2,'y':8},{'ok':True},before,after)
    assert proof.status=='observed_change'
    goal=verify_goal(interpret_goal('افتح المفكرة'),[{'status':'ok','tool':'click','verification':proof.status}])
    assert goal.status=='unverified'


def test_file_integrity_checks(tmp_path):
    src=tmp_path/'original.txt';dst=tmp_path/'copied.txt'
    src.write_text('correct',encoding='utf-8');dst.write_text('other',encoding='utf-8')
    assert verify_action('copy',{'src':str(src),'dst':str(dst)},{'ok':True}).status=='contradicted'
    dst.write_text('correct',encoding='utf-8')
    assert verify_action('copy',{'src':str(src),'dst':str(dst)},{'ok':True}).status=='verified'
    assert verify_action('create_dir',{'path':str(tmp_path/'missing')},{'ok':True}).status=='contradicted'


def test_no_automatic_model_claim_without_actions():
    assert verify_goal(interpret_goal('افتح المفكرة'),[]).status=='unverified'
    assert verify_goal(interpret_goal('افتح المفكرة و اكتب فيها'),[
        {'tool':'open_app','status':'ok','verification':'verified'}]).status=='unverified'


def test_volume_readback_must_match_requested_level():
    assert verify_action('set_volume',{'percent':35},{'percent':35}).status=='verified'
    assert verify_action('set_volume',{'percent':35},{'percent':90}).status=='unverified'


def test_anchored_ui_safety_and_approval(tmp_path):
    policy=Policy(enabled=True)
    assert policy.evaluate('click',{'element_id':'ui-0'})[1]==Decision.ASK
    assert policy.evaluate('click',{'element_id':'ui-0','signature':'a'*24})[1]==Decision.ALLOW
    assert policy.evaluate('invoke_ui',{'element_id':'ui-0','signature':'a'*24})[1]==Decision.ASK
    trusted=Policy(enabled=True,mode=Mode.TRUSTED)
    assert trusted.evaluate('invoke_ui',{'element_id':'ui-0','signature':'a'*24})[1]==Decision.ASK
    # Use an absolute, known-safe test folder. Relative paths would resolve
    # inside the release build's %LOCALAPPDATA%/Bq staging tree on Windows,
    # which correctly remains blocked by the security policy.
    safe_file = str(tmp_path / 'safe.txt')
    assert trusted.evaluate('delete', {'path': safe_file})[1] == Decision.ASK
    with pytest.raises(ValueError):validate('invoke_ui',{'element_id':'ui-0','signature':'not-valid'})


def test_staged_appdata_working_directory_stays_protected(tmp_path, monkeypatch):
    """Reproduce Windows %LOCALAPPDATA%/Bq staging path on any host OS.

    The old regression accidentally tested a relative safe.txt inside this
    protected build directory. It was right for BARQ to BLOCK that delete.
    """
    staging = tmp_path / 'AppData' / 'Local' / 'Bq' / 'build'
    staging.mkdir(parents=True)
    monkeypatch.chdir(staging)
    trusted = Policy(enabled=True, mode=Mode.TRUSTED,
                     allowed_folders=[str(tmp_path)])
    assert trusted.evaluate('delete', {'path': 'safe.txt'})[1] == Decision.BLOCK
    # Unrelated explicit user files still require approval in trusted mode.
    assert trusted.evaluate('delete', {'path': str(tmp_path / 'safe.txt')})[1] == Decision.ASK


def test_accessibility_tools_validate_without_reaching_windows():
    assert validate('list_apps',{})=={}
    assert validate('find_ui_elements',{'query':'save'})=={'query':'save'}
    assert validate('set_ui_text',{'element_id':'ui-5','signature':'a'*24,'text':'مرحبا'})['text']=='مرحبا'


@pytest.mark.asyncio
async def test_llm_done_only_needs_review_without_observed_goal(tmp_path):
    class PlannerStub:
        async def plan(self,*a):return type('P',(),{'steps':['inspect screen']})()
        async def next(self,*a):return type('A',(),{'done':True})()
    mgr=Manager(FakeAdapter(),policy=Policy(enabled=True,allowed_folders=[str(tmp_path)]),
                audit=Audit(tmp_path/'audit.jsonl'),planner=PlannerStub())
    mgr.start('افتح المفكرة',source='voice')
    await mgr._job
    assert mgr.current.status=='needs_review'
    assert mgr.current.phase=='verify'
    assert mgr.current.public()['goal_proof']['status']=='unverified'
    assert not any(x['event']=='goal_verified' for x in mgr.audit.recent(mgr.current.id))


@pytest.mark.asyncio
async def test_single_dir_operation_verified_and_documented(tmp_path):
    path=tmp_path/'newfolder'
    class PlannerStub:
        def __init__(self):self.called=0
        async def plan(self,*a):return type('P',(),{'steps':['create folder']})()
        async def next(self,*a):
            self.called+=1
            return type('A',(),{'done':False,'action':'create_dir','args':{'path':str(path)}})() if self.called==1 else type('A',(),{'done':True})()
    mgr=Manager(FakeAdapter(),policy=Policy(enabled=True,allowed_folders=[str(tmp_path)]),
                audit=Audit(tmp_path/'audit.jsonl'),planner=PlannerStub())
    mgr.start('انشئ مجلد',source='text')
    await mgr._job
    assert path.is_dir() and mgr.current.status=='completed'
    assert mgr.current.history[0]['verification']=='verified'
    assert mgr.current.public()['goal_proof']['status']=='verified'


def test_windows_start_menu_is_discoverable_without_scanning_appdata(tmp_path,monkeypatch):
    """Known Start Menu paths are metadata; protected AppData contents stay blocked."""
    import launcher.indexes as mod
    from computer_control.safety.policy import sensitive
    root=tmp_path/'Microsoft'/'Windows'/'Start Menu'/'Programs'
    root.mkdir(parents=True);(root/'Example App.lnk').write_text('shortcut',encoding='utf-8')
    monkeypatch.setenv('APPDATA',str(tmp_path))
    monkeypatch.delenv('PROGRAMDATA',raising=False)
    monkeypatch.setattr(mod.sys,'platform','win32')
    monkeypatch.setattr(mod.shutil,'which',lambda _name: None)
    names=[a['label'] for a in mod.Index(path=tmp_path/'index.sqlite').apps()]
    assert 'Example App' in names
    assert sensitive(str(tmp_path/'AppData'/'Roaming'/'Microsoft'/'Credentials'))



@pytest.mark.asyncio
async def test_spoken_create_directory_checks_real_filesystem(tmp_path):
    path=tmp_path/'BARQ-Voice-Test'
    mgr=Manager(FakeAdapter(),policy=Policy(enabled=True,allowed_folders=[str(tmp_path)]),
                audit=Audit(tmp_path/'voice-audit.jsonl'),planner=object())
    mgr.start(f'اعمل فولدر باسم "{path}"',source='voice')
    await mgr._job
    assert path.is_dir()
    assert mgr.current.status=='completed'
    assert mgr.current.public()['goal_proof']['status']=='verified'
