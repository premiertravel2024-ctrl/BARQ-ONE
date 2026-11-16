"""Executable regression tests; never touch the real Windows desktop."""
from types import SimpleNamespace
from pathlib import Path
import asyncio
import pytest

from computer_control.safety.policy import Policy, Mode, Decision
from computer_control.tools.schema import validate
from computer_control.adapters.base import FakeAdapter
from computer_control.executor.manager import Manager
from computer_control.audit.journal import Audit
from computer_control.tools import windows_quick
from voice.computer_tools import dispatch_computer_tool, LIVE_COMPUTER_TOOLS


@pytest.mark.parametrize('tool,args',[
    ('set_volume',{'percent':0}),('set_volume',{'percent':100}),
    ('set_brightness',{'percent':30}),('open_windows_settings',{'page':'sound'}),
    ('get_volume',{}),('get_brightness',{})
])
def test_tools_registered(tool,args):
    assert validate(tool,args)==args
    assert Policy(enabled=True).evaluate(tool,args)[1]==Decision.ALLOW

@pytest.mark.parametrize('level',[-1,101,True,None,'80',80.5])
def test_reject_bad_levels(level):
    assert Policy(enabled=True).evaluate('set_volume',{'percent':level})[1]==Decision.BLOCK

@pytest.mark.parametrize('page',['security','cmd','../privacy','ms-settings:windowsupdate',''])
def test_no_unlisted_windows_page(page):
    assert Policy(enabled=True).evaluate('open_windows_settings',{'page':page})[1]==Decision.BLOCK

def test_observe_mode_blocks_actions():
    p=Policy(enabled=True,mode=Mode.OBSERVE)
    assert p.evaluate('set_volume',{'percent':15})[1]==Decision.BLOCK
    assert p.evaluate('get_volume',{})[1]==Decision.ALLOW


def test_quick_actions_require_consent_and_write_audit(tmp_path,monkeypatch):
    events=[]
    monkeypatch.setattr(windows_quick,'set_volume',lambda level:events.append(('volume',level)) or {'percent':level})
    manager=Manager(FakeAdapter(),policy=Policy(enabled=False),audit=Audit(tmp_path/'audit.jsonl'))
    with pytest.raises(RuntimeError,match='disabled'):
        manager.desktop_quick('set_volume',{'percent':33})
    assert not events
    manager.policy.enabled=True
    assert manager.desktop_quick('set_volume',{'percent':33})['status']=='ok'
    assert events==[('volume',33)]
    assert 'set_volume' in (tmp_path/'audit.jsonl').read_text(encoding='utf-8')


def test_quick_actions_respect_ask_always(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(windows_quick,'set_brightness',lambda level:calls.append(level))
    m=Manager(FakeAdapter(),policy=Policy(enabled=True,mode=Mode.ASK),audit=Audit(tmp_path/'audit.jsonl'))
    assert m.desktop_quick('set_brightness',{'percent':30})['status']=='approval_required'
    assert calls==[]


def test_quick_does_not_bypass_running_task(tmp_path,monkeypatch):
    m=Manager(FakeAdapter(),policy=Policy(enabled=True),audit=Audit(tmp_path/'audit.jsonl'))
    m.current=SimpleNamespace(status='running')
    assert m.desktop_quick('set_volume',{'percent':60})['status']=='busy'


@pytest.mark.asyncio
async def test_voice_setting_uses_audited_manager(monkeypatch):
    class M:
        policy=SimpleNamespace(enabled=True)
        def desktop_quick(self,tool,args,source):
            assert tool=='set_volume' and args=={'percent':45} and source=='voice'
            return {'status':'ok','result':{'percent':45}}
    monkeypatch.setattr('voice.computer_tools.sys.platform','win32')
    response=await dispatch_computer_tool('control_windows_setting',{'setting':'volume','percent':45},manager_instance=M())
    assert response['status']=='ok' and response['result']['percent']==45
    response=await dispatch_computer_tool('control_windows_setting',{'setting':'volume','percent':'45'},manager_instance=M())
    assert response['status']=='needs_clarification'

@pytest.mark.asyncio
async def test_voice_setting_cannot_override_disabled_permission(monkeypatch):
    monkeypatch.setattr('voice.computer_tools.sys.platform','win32')
    class M:
        policy=SimpleNamespace(enabled=False)
        def desktop_quick(self,*args,**kwargs):raise AssertionError('must not execute')
    assert (await dispatch_computer_tool('control_windows_setting',{'setting':'volume','percent':45},manager_instance=M()))['status']=='disabled'


def test_windows_native_controls_mocked(monkeypatch):
    class Audio:
        volume_percent=21.0
    import sys
    a=Audio()
    monkeypatch.setitem(sys.modules,'pycaw',SimpleNamespace())
    monkeypatch.setitem(sys.modules,'pycaw.pycaw',SimpleNamespace(AudioUtilities=SimpleNamespace(GetSpeakers=lambda:a)))
    assert windows_quick.set_volume(60)['percent']==60
    assert windows_quick.get_volume()['percent']==60
    b=SimpleNamespace(set_brightness=lambda x,display=0:None,get_brightness=lambda display=0:[34])
    monkeypatch.setitem(sys.modules,'screen_brightness_control',b)
    assert windows_quick.set_brightness(34)['percent']==34
    assert windows_quick.get_brightness()['percent']==34


def test_voice_tool_api_has_no_raw_os_access():
    definitions=LIVE_COMPUTER_TOOLS[0]['function_declarations']
    names={x['name'] for x in definitions}
    assert 'control_windows_setting' in names
    assert not {'run_command','execute_shell','delete','approve','click'}&names

@pytest.mark.asyncio
async def test_voice_relative_setting_only_after_device_consent(monkeypatch):
    monkeypatch.setattr('voice.computer_tools.sys.platform','win32')
    calls=[]
    class M:
        policy=SimpleNamespace(enabled=True)
        def desktop_quick(self,tool,args,source):
            calls.append((tool,args))
            if tool=='get_volume':return {'status':'ok','result':{'percent':96}}
            return {'status':'ok','result':args}
    result=await dispatch_computer_tool('control_windows_setting',{'setting':'volume','action':'up'},manager_instance=M())
    assert result['result']['percent']==100
    assert calls==[('get_volume',{}),('set_volume',{'percent':100})]

@pytest.mark.asyncio
async def test_voice_relative_setting_rejects_oversized_step(monkeypatch):
    monkeypatch.setattr('voice.computer_tools.sys.platform','win32')
    class M:
        policy=SimpleNamespace(enabled=True)
        def desktop_quick(self,*a,**k):raise AssertionError('No execution on invalid step')
    result=await dispatch_computer_tool('control_windows_setting',{'setting':'brightness','action':'down','percent':80},manager_instance=M())
    assert result['status']=='needs_clarification'


def test_shortcut_must_not_wait_for_permission_http_before_opening_microphone():
    source=(Path(__file__).parents[1]/'frontend/src/App.tsx').read_text(encoding='utf-8')
    segment=source.split('function openConsentedVoiceSession(){',1)[1].split('\n}',1)[0]
    assert 'dispatchEvent' in segment
    assert 'await' not in segment and 'fetch(' not in segment
    assert 'computerEnabled:false' not in source
    assert 'refreshComputerVoiceConsent' in source


def test_voice_consent_is_persisted_only_via_settings_endpoint():
    source=(Path(__file__).parents[1]/'frontend/src/components/layout/VoiceSettings.tsx').read_text(encoding='utf-8')
    assert "setWakeOption('wake_computer_enabled',e.target.checked)" in source
    assert "field==='wake_computer_enabled'" in source
    assert "barq-voice-computer-permission-updated" in source
