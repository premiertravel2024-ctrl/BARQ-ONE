"""BARQ user-initiated read-only Windows questions and discoverable packaging."""
from pathlib import Path
from unittest.mock import patch
import pytest
from core import windows_facts as facts
from core.persona import instant_identity_reply

SAMPLE={
 'operating_system':'Windows','windows_version':'11','architecture':'AMD64',
 'cpu':'Intel Core i7','logical_cpu_count':20,'ram_gb':16.0,
 'ram_available_gb':9.1,'drives':[{'drive':'C:\\','total_gb':512,'free_gb':200}],
 'battery_percent':50,'charging':True,'process_names':['chrome.exe','Code.exe']
}

@pytest.fixture
def windows(monkeypatch):
 monkeypatch.setattr(facts.platform,'system',lambda:'Windows')
 monkeypatch.setattr(facts,'snapshot',lambda:SAMPLE)
 return monkeypatch

@pytest.mark.parametrize('q', ['الرام كام', 'مواصفات الجهاز', 'البطارية كام',
 'البرامج الشغالة ايه', 'معالجي ايه','قولي اصدار ويندوز', 'مساحة الهارد كام'])
def test_read_only_answer_is_from_device_and_requires_consent(windows,q):
 windows.setattr(facts,'_is_enabled',lambda:False)
 assert 'الإعدادات' in facts.answer(q)
 windows.setattr(facts,'_is_enabled',lambda:True)
 got=facts.answer(q)
 assert got and 'الإعدادات' not in got
 if 'البرامج' in q:assert 'chrome.exe' in got and '16.0' not in got
 if q.startswith('الرام'):assert '16.0' in got

@pytest.mark.parametrize('q',['افتح إعدادات ويندوز','شغل البرامج','اكتب معلومات عن الويندوز', 'ترجم رام','افتح ملف'])
def test_queries_do_not_intercept_actions(windows,q):
 windows.setattr(facts,'_is_enabled',lambda:True)
 assert facts.answer(q) is None

@pytest.mark.parametrize('q',['انا مين','فاكرني','اسمي ايه','مين اللي برمجك'])
def test_ashraf_is_recognized_by_barq_without_a_provider(q):
 assert 'أشرف محمد' in instant_identity_reply([{'role':'user','content':q}])

def test_installer_directory_is_user_selectable_and_model_is_visible():
 root=Path(__file__).resolve().parents[1]
 setup=(root/'scripts/installer.iss').read_text(encoding='utf-8')
 assert 'DisableDirPage=no' in setup
 assert 'DefaultDirName={localappdata}\\Programs\\AI Router Agent' in setup
 assert 'Name: "{app}\\models\\wake"' in setup
 assert "WakeExe := ExpandConstant(" in setup
 model=(root/'scripts/install_arabic_wake.py').read_text(encoding='utf-8')
 assert "_APP/'models'/'wake'" in model
 assert 'model.zip' in model
 wake=(root/'scripts/barq_wake_vosk.py').read_text(encoding='utf-8')
 assert '_LEGACY_MODEL' in wake and '_PACKAGED_MODEL' in wake

def test_voice_function_declaration_is_read_only():
 from voice.computer_tools import LIVE_COMPUTER_TOOLS
 declarations=LIVE_COMPUTER_TOOLS[0]['function_declarations']
 names={item['name'] for item in declarations}
 assert 'get_pc_system_facts' in names
 assert 'run_command' not in names
