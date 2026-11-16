"""CPU/GPU temperature must be measured, never guessed, and available to Live."""
import json
import pytest
from core import hardware_sensors as hw
from core import windows_facts as facts
from voice import computer_tools

@pytest.fixture
def active_windows(monkeypatch):
    monkeypatch.setattr(facts.platform,'system',lambda:'Windows')
    monkeypatch.setattr(facts,'_is_enabled',lambda:True)
    monkeypatch.setattr(hw,'_is_windows',lambda:True)
    return monkeypatch

def test_lhm_selects_cpu_package_and_gpu_sensor(active_windows):
    values=[
        {'Name':'CPU Core #1','Identifier':'/intelcpu/0/temperature/0','SensorType':'Temperature','Value':65},
        {'Name':'CPU Package','Identifier':'/intelcpu/0/temperature/4','SensorType':'Temperature','Value':71.2},
        {'Name':'GPU Core','Identifier':'/nvidiagpu/0/temperature/0','SensorType':'Temperature','Value':55},
        {'Name':'Motherboard','Identifier':'/lpc/0/temperature/0','SensorType':'Temperature','Value':38},
    ]
    active_windows.setattr(hw.shutil,'which',lambda _: 'powershell.exe')
    active_windows.setattr(hw,'_run',lambda cmd,timeout:json.dumps(values))
    got=hw.read_local_temperatures()
    assert got['cpu_c']==71.2 and got['cpu_sensor']=='CPU Package'
    assert got['gpu_c']==55 and got['provider']

def test_cpu_temperature_query_not_confused_with_processor_name(active_windows):
    active_windows.setattr(hw,'snapshot',lambda **kwargs:{'cpu_c':76,'cpu_sensor':'CPU Package','provider':'LibreHardwareMonitor'})
    active_windows.setattr(facts,'snapshot',lambda:{'cpu':'Intel Core i7','logical_cpu_count':20})
    for q in ('درجة حرارة المعالج كام؟','الـ CPU حرارته كام دلوقتي','اللابتوب سخن ولا لا'):
        assert '76' in facts.answer(q)
        assert 'Intel Core i7' not in facts.answer(q)

def test_no_fake_temperature_when_provider_missing(active_windows):
    active_windows.setattr(hw,'snapshot',lambda **kwargs:{'cpu_c':None,'reason':'sensor_provider_unavailable'})
    message=facts.answer('حرارة المعالج كام')
    assert 'مش متاحة' in message and 'LibreHardwareMonitor' in message
    assert '40' not in message

def test_explicit_read_only_temperature_does_not_need_desktop_control(active_windows):
    active_windows.setattr(facts,'_is_enabled',lambda:False)
    active_windows.setattr(hw,'snapshot',lambda **kw:{'cpu_c':68.2,'cpu_sensor':'CPU Package'})
    assert '68.2' in facts.answer('حرارة المعالج كام؟')
    assert 'الإعدادات' in facts.answer('سعة الرام كام؟')

def test_sensor_errors_are_bounded_and_zero_is_not_reported(active_windows):
    active_windows.setattr(hw.shutil,'which',lambda _: 'powershell.exe')
    active_windows.setattr(hw,'_run',lambda cmd,timeout:'broken-json')
    got=hw.read_local_temperatures()
    assert got['cpu_c'] is None and got['reason']=='sensor_provider_unavailable'
    assert hw._valid_temperature('0') is None
    assert hw._valid_temperature('nan') is None
    assert hw._valid_temperature(80.1)==80.1

def test_gpu_fallback_from_local_nvidia_driver(active_windows):
    active_windows.setattr(hw.shutil,'which',lambda x:'nvidia-smi' if x=='nvidia-smi' else None)
    active_windows.setattr(hw,'_run',lambda cmd,timeout:'63, 22, 1024, 8192')
    got=hw.snapshot()
    assert got['gpu_c']==63 and got['vram_total_mb']==8192
    active_windows.setattr(facts,'snapshot',lambda:{})
    assert '63' in facts.answer('درجة حرارة كارت الشاشة كام؟')

def test_no_weather_hijack(active_windows):
    assert facts.answer('درجة الحرارة بره كام') is None

def test_read_only_live_tool_declaration_covers_thermal_queries():
    x=next(x for x in computer_tools.LIVE_COMPUTER_TOOLS[0]['function_declarations'] if x['name']=='get_pc_system_facts')
    assert 'temperature' in x['description'].lower()
    assert 'get_pc_system_facts' in computer_tools.LIVE_CONTROL_INSTRUCTION

@pytest.mark.asyncio
async def test_voice_tool_delivers_temperature(monkeypatch,active_windows):
    from types import SimpleNamespace
    class Manager:
        policy=SimpleNamespace(enabled=True)
    active_windows.setattr(facts,'_answer_sensor_question',lambda q:'حرارة المعالج 68 درجة مئوية')
    response=await computer_tools.dispatch_computer_tool('get_pc_system_facts',{'question':'درجة حرارة المعالج كام'},manager_instance=Manager())
    assert response['status']=='ok' and '68' in response['message']
