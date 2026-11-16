import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from computer_control.adapters.windows_mcp import MCPEnhancedAdapter
from mcp.windows_client import (WindowsMCPClient, BridgeUnavailable,
                                 BridgeCallFailed, ALLOWED_TOOLS, installation_status)


class Native:
    def __init__(self):self.actions=[]
    def act(self,t,a):self.actions.append((t,a));return {'native':True}
    def _point(self,args):
        if args.get('element_id'):
            return 44,55
        return args['x'],args['y']
    def perceive(self):return {'native':'perception'}
    def check_abort(self):return False


class Bridge:
    def __init__(self,exc=None):self.calls=[];self.exc=exc
    def call(self,tool,args):
        self.calls.append((tool,args))
        if self.exc:raise self.exc('test')
        return {'bridge':'Windows-MCP','ok':True}


def test_click_through_local_mcp():
    b=Bridge();n=Native();a=MCPEnhancedAdapter(n,b)
    assert a.act('click',{'x':10,'y':20})['ok']
    assert b.calls==[('Click',{'loc':[10,20],'clicks':1,'button':'left'})]
    assert not n.actions


def test_double_click_and_drag_are_atomic():
    b=Bridge();a=MCPEnhancedAdapter(Native(),b)
    a.act('double_click',{'x':1,'y':2})
    a.act('drag',{'from':[12,19],'to':[66,70]})
    assert b.calls[0][1]['clicks']==2
    assert b.calls[1]==('Move',{'loc':[66,70], 'from_loc':[12,19],'drag':True})


def test_stale_target_rejected_before_bridge_call():
    b=Bridge();a=MCPEnhancedAdapter(Native(),b)
    with pytest.raises(ValueError,match='signature'):
        a.act('click',{'element_id':'ui-4'})
    assert b.calls==[]


def test_hotkey_and_open_app_are_strictly_mapped():
    b=Bridge();a=MCPEnhancedAdapter(Native(),b)
    a.act('hotkey',{'keys':['ctrl','shift','esc']})
    a.act('open_app',{'name':'Notepad'})
    assert b.calls==[('Shortcut',{'shortcut':'Ctrl+Shift+Esc'}),('App',{'mode':'launch','name':'Notepad'})]


def test_missing_bridge_falls_back_to_existing_adapter():
    n=Native();b=Bridge(BridgeUnavailable);a=MCPEnhancedAdapter(n,b)
    assert a.act('click',{'x':10,'y':20})=={'native':True}
    assert len(n.actions)==1


def test_unknown_result_never_replays_click():
    n=Native();b=Bridge(BridgeCallFailed);a=MCPEnhancedAdapter(n,b)
    with pytest.raises(BridgeCallFailed):a.act('click',{'x':10,'y':20})
    assert n.actions==[]


def test_non_gui_tools_never_enter_windows_mcp():
    n=Native();b=Bridge();a=MCPEnhancedAdapter(n,b)
    a.act('invoke_ui',{'element_id':'ui-4','signature':'x'*24})
    a.act('open_file',{'path':'example.txt'})
    assert b.calls==[]
    assert len(n.actions)==2


def test_only_allowlisted_mcp_tools_and_no_network():
    assert {'PowerShell','Registry','FileSystem','Process','Clipboard','Scrape'}.isdisjoint(ALLOWED_TOOLS)
    code=Path(__file__).resolve().parents[1].joinpath('mcp/windows_client.py').read_text()
    assert "'stdio'" in code
    assert "'--tools'" in code
    assert 'ANONYMIZED_TELEMETRY' in code


def test_status_reports_install_required_on_non_windows():
    if sys.platform != 'win32':
        assert installation_status()['installed'] is False
    assert installation_status()['version_pinned'] == '0.8.8'


def test_installer_contains_real_online_install_not_placeholder():
    root=Path(__file__).resolve().parents[1]
    script=(root/'scripts/install_windows_mcp.ps1').read_text()
    iss=(root/'scripts/installer.iss').read_text()
    assert 'uv tool install' in script
    assert 'windows-mcp==' in script
    assert '--python 3.14' in script
    assert 'install_windows_mcp.ps1' in iss
    assert 'Tasks: windowsmcp' in iss
    assert 'scripts\\install_windows_mcp.ps1' in iss


def test_generic_mcp_cannot_bypass_barq_computer_control_policy():
    from mcp import bridge
    with pytest.raises(bridge.MCPError):
        bridge.register('windows-mcp','uvx',['windows-mcp','serve'],True,persist=False)
    with pytest.raises(bridge.MCPError):
        bridge.register('fakeserver','uvx',['windows-mcp','serve'],True,persist=False)


def test_focused_text_typing_stays_native_without_unsafe_pointer_click():
    n=Native();b=Bridge();a=MCPEnhancedAdapter(n,b)
    assert a.act('type_text',{'text':'مرحبا'}) == {'native': True}
    assert b.calls == []
