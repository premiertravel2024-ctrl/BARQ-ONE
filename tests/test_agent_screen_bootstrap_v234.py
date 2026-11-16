from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import pytest
from computer_control.adapters.base import FakeAdapter,Perception
from computer_control.tools import screen
from voice.brain_bridge import action_route,safe_cloud_view
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('text',['شوف اللي على الشاشة','اقرا الشاشة','read the screen','look at my screen'])
def test_explicit_screen_voice_route(text):
    assert action_route(text)=='read_current_screen'

def test_uia_reader_filters_password_deduplicates_and_never_returns_image():
    adapter=FakeAdapter();adapter.screen=Perception(window='Editor',elements=[{'name':'A long visible document line '*4},{'name':'secret','is_password':True},{'name':'another secret','role':'Password'},{'name':'A long visible document line '*4}],screenshot_png=b'private')
    result=screen.read_screen(adapter,ocr=lambda:pytest.fail('UIA sufficient'))
    assert result['status']=='ok' and result['source']=='uia'
    assert result['text'].count('A long')==4
    assert 'secret' not in result['text'] and 'screenshot_png' not in result and result['screenshot_uploaded'] is False

def test_ocr_fallback_only_when_uia_insufficient():
    result=screen.read_screen(FakeAdapter(),ocr=lambda:{'text':'Visible raster document','language':'en'})
    assert result['text']=='Visible raster document' and result['source']=='windows_ocr'

def test_empty_screen_is_not_success():
    adapter=FakeAdapter();adapter.screen=Perception()
    result=screen.read_screen(adapter,ocr=lambda:{'text':'','error':'language unavailable'})
    assert result['status']=='unavailable' and result['error']=='language unavailable'

def test_perception_failure_is_actionable_not_crash():
    adapter=SimpleNamespace(perceive=lambda:(_ for _ in ()).throw(RuntimeError('private diagnostics')))
    result=screen.read_screen(adapter)
    assert result['status']=='unavailable' and 'private' not in str(result)

@pytest.mark.parametrize('failed',[False,True])
def test_ocr_fixed_argv_timeout_and_temp_cleanup(monkeypatch,failed):
    monkeypatch.setattr(screen.sys,'platform','win32')
    paths=[]
    class Image:
        def save(self,path,**kwargs):paths.append(path);path.write_bytes(b'fixture')
    def runner(argv,**kwargs):
        assert argv[0]=='powershell.exe' and argv[-2]=='-ImagePath'
        assert kwargs['shell'] is False and kwargs['timeout']==15 and paths[0].exists()
        if failed:raise subprocess.TimeoutExpired(argv,15)
        return SimpleNamespace(returncode=0,stdout='{"text":"ظاهر في الشاشة","language":"ar"}')
    result=screen.ocr_active_window(capture=Image,runner=runner)
    assert not paths[0].exists() and not paths[0].parent.exists()
    assert bool(result.get('error')) is failed

def test_cloud_receives_no_local_screen_text():
    result=safe_cloud_view({'status':'ok','spoken_ar':'قريت الشاشة','cards':[{'label':'private local text'}]})
    assert result['cards']==[] and 'private' not in str(result)

def test_ocr_helper_in_frozen_binary_and_installer():
    build=(ROOT/'scripts/build_windows.ps1').read_text()
    installer=(ROOT/'scripts/installer.iss').read_text()
    assert 'scripts/read_screen_ocr.ps1;scripts' in build
    for name in ('read_screen_ocr.ps1','ensure_webview2.ps1','build_prerequisites.ps1'):
        assert name in installer
    assert build.index('& $prerequisiteScript') < build.index('if (-not (Get-Command py')

def test_powershell_bootstrap_behavior_when_runtime_available():
    import shutil
    pwsh=shutil.which('pwsh') or ('/tmp/barq-pwsh/pwsh' if Path('/tmp/barq-pwsh/pwsh').is_file() else shutil.which('powershell.exe'))
    if not pwsh:pytest.skip('PowerShell runtime unavailable')
    result=subprocess.run([pwsh,'-NoProfile','-File',str(ROOT/'scripts/test_build_prerequisites.ps1')],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'checks passed: 15' in result.stdout

@pytest.mark.parametrize('text',['متقراش الشاشة','لو قلت شوف الشاشة','ازاي شوف الشاشة بتشتغل','what does read screen mean'])
def test_non_commands_do_not_read_screen(text):
    assert not screen.is_screen_request(text)
