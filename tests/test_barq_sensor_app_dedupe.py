"""Regression tests for BARQ local application and temperature integration."""
from pathlib import Path
from unittest.mock import patch


def test_chrome_shortcut_and_executable_are_one_application():
    from computer_control.tools import app_index
    apps = [
        {'label': 'Google Chrome', 'path': r'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Google Chrome.lnk', 'appid': None},
        {'label': 'Chrome', 'path': r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', 'appid': None},
    ]
    app_index._apps_cached.cache_clear()
    with patch.object(app_index, '_apps_cached', return_value=(__import__('time').monotonic(), apps)):
        resolved = app_index.resolve_app('جوجل كروم')
    assert resolved['path'].lower().endswith('chrome.exe')


def test_standalone_hardware_monitor_discovery(tmp_path, monkeypatch):
    from core import hardware_sensors
    from core import paths as core_paths
    from core import tool_locator

    vendor = tmp_path / 'Program Files' / 'LibreHardwareMonitor'
    vendor.mkdir(parents=True)
    executable = vendor / 'LibreHardwareMonitor.exe'
    executable.write_bytes(b'placeholder')

    # Isolate the discovery roots from the developer's real installations.
    # An existing BARQ toolkit or running LibreHardwareMonitor must not take
    # precedence over this test's synthetic Program Files tree.
    monkeypatch.setattr(hardware_sensors.sys, 'platform', 'win32')
    monkeypatch.setenv('ProgramFiles', str(tmp_path / 'Program Files'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'LocalAppData'))
    monkeypatch.delenv('ProgramFiles(x86)', raising=False)
    monkeypatch.setattr(core_paths, 'resource', lambda *parts: tmp_path / 'resources')
    monkeypatch.setattr(tool_locator, 'hardware_monitor_folder', lambda: None)
    monkeypatch.setattr(hardware_sensors, '__file__',
                        str(tmp_path / 'isolated-core' / 'hardware_sensors.py'))
    monkeypatch.setattr(hardware_sensors, '_running_monitor_executable', lambda: None)

    assert hardware_sensors._monitor_executable() == executable


def test_package_sensor_preferred_to_core_max():
    from core.hardware_sensors import _collect_temperatures
    values = [
        {'Name': 'Core Max', 'Identifier': '/intelcpu/0/temperature/0', 'Value': 65.0},
        {'Name': 'CPU Package', 'Identifier': '/intelcpu/0/temperature/1', 'Value': 64.0},
    ]
    result = _collect_temperatures(values)
    assert result['cpu_c'] == 64.0
    assert result['cpu_sensor'] == 'CPU Package'


def test_launcher_resolver_collapses_chrome_shortcut_and_exe(tmp_path):
    from launcher.indexes import Index
    from launcher.resolver import Resolver
    from computer_control.safety.policy import Policy

    exe = tmp_path / 'chrome.exe'
    exe.write_bytes(b'stub')
    shortcut = tmp_path / 'Google Chrome.lnk'
    shortcut.write_bytes(b'stub')
    apps = [
        {'label': 'Google Chrome', 'path': str(shortcut), 'appid': None},
        {'label': 'Chrome', 'path': str(exe), 'appid': None},
    ]
    resolver = Resolver(Index(tmp_path / 'apps.sqlite', roots=[]), Policy(), app_source=lambda: apps)
    result = resolver.resolve('افتح جوجل كروم')
    assert result is not None and result.decision in ('auto', 'ask_approval')
    assert len(result.candidates) == 1
    assert result.candidates[0]['path_or_appid'] == str(exe)


def test_launcher_does_not_merge_two_different_executables(tmp_path):
    from launcher.indexes import Index
    from launcher.resolver import Resolver
    from computer_control.safety.policy import Policy

    first = tmp_path / 'one' / 'chrome.exe'
    second = tmp_path / 'two' / 'chrome.exe'
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b'stub')
    second.write_bytes(b'stub')
    resolver = Resolver(
        Index(tmp_path / 'apps.sqlite', roots=[]), Policy(),
        app_source=lambda: [
            {'label': 'Chrome', 'path': str(first), 'appid': None},
            {'label': 'Chrome', 'path': str(second), 'appid': None},
        ])
    result = resolver.resolve('افتح جوجل كروم')
    assert result is not None and result.decision == 'choose'
    assert len(result.candidates) == 2


def test_cpu_package_can_be_read_using_dll_without_wmi(monkeypatch, tmp_path):
    from core import hardware_sensors as hw

    monitor = tmp_path / 'LibreHardwareMonitor.exe'
    monitor.write_bytes(b'stub')
    (tmp_path / 'LibreHardwareMonitorLib.dll').write_bytes(b'stub')
    monkeypatch.setattr(hw, '_is_windows', lambda: True)
    monkeypatch.setattr(hw.shutil, 'which', lambda _: 'powershell.exe')
    monkeypatch.setattr(hw, '_query_lhm', lambda *args, **kwargs: None)
    monkeypatch.setattr(hw, '_monitor_executable', lambda: monitor)
    monkeypatch.setattr(hw, '_query_local_library', lambda *args, **kwargs:
        '[{"Name":"CPU Package","Identifier":"/intelcpu/0/temperature/0","Value":64.0,"SensorType":"Temperature"}]')
    result = hw.read_local_temperatures()
    assert result['cpu_c'] == 64.0
    assert result['provider'] == 'LibreHardwareMonitor (local .NET)'


def test_openhub_queue_is_not_in_catalog_and_voice_flow_is_removed():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] /
            'frontend' / 'src' / 'pages' / 'BarqOne.tsx').read_text(encoding='utf-8')
    assert 'function CommandFlow(' not in page
    assert '<CommandFlow' not in page
    assert "mode==='installed'&&!!jobs.length" in page
    assert "page==='voice'&&<Hologram onStart={onVoice}/>" in page


def test_localized_chrome_commands_choose_one_installed_app(tmp_path):
    from launcher.indexes import Index
    from launcher.resolver import Resolver
    from computer_control.safety.policy import Policy

    shortcut = tmp_path / 'Google Chrome.lnk'
    executable = tmp_path / 'chrome.exe'
    shortcut.write_bytes(b'stub')
    executable.write_bytes(b'stub')
    resolver = Resolver(Index(tmp_path / 'local.sqlite', roots=[]), Policy(),
                        app_source=lambda: [
                            {'kind':'app', 'label':'Google Chrome', 'path':str(shortcut), 'appid':None},
                            {'kind':'app', 'label':'Chrome', 'path':str(executable), 'appid':None},
                        ])
    for phrase in ('افتح كروم', 'افتح الكروم', 'افتح جوجل كروم', 'شغل جوجل كروم',
                   'open Chrome', 'open Google Chrome'):
        result = resolver.resolve(phrase)
        assert result is not None, phrase
        assert result.decision in ('auto', 'ask_approval'), (phrase, result.decision)
        assert len(result.candidates) == 1, (phrase, result.candidates)
        assert result.candidates[0]['path_or_appid'] == str(executable)


def test_arabic_word_alias_matches_english_vendor_label(tmp_path):
    from launcher.indexes import Index
    from launcher.resolver import Resolver
    from computer_control.safety.policy import Policy

    shortcut = tmp_path / 'Microsoft Word.lnk'
    executable = tmp_path / 'WINWORD.exe'
    shortcut.write_bytes(b'stub')
    executable.write_bytes(b'stub')
    resolver = Resolver(Index(tmp_path / 'word.sqlite', roots=[]), Policy(),
                        app_source=lambda: [
                            {'kind':'app','label':'Microsoft Word','path':str(shortcut),'appid':None},
                            {'kind':'app','label':'Word','path':str(executable),'appid':None},
                        ])
    result = resolver.resolve('افتح الوورد')
    assert result is not None and result.decision != 'choose'
    assert len(result.candidates) == 1
    # Office documents have a dedicated, safer launcher route that runs
    # before generic app-name matching. Either route must remain unambiguous.
    assert result.candidates[0]['path_or_appid'] in (str(executable), 'office:word')


def test_arabic_chat_opens_registered_chrome_without_duplicate_choice(tmp_path, monkeypatch):
    from computer_control.safety.policy import Policy
    from launcher.indexes import Index
    from launcher.resolver import Resolver
    import launcher.api as launcher_api

    link = tmp_path / 'Google Chrome.lnk'
    executable = tmp_path / 'chrome.exe'
    link.write_bytes(b'stub')
    executable.write_bytes(b'stub')
    local = Resolver(Index(tmp_path / 'app.sqlite', roots=[]), Policy(),
                     app_source=lambda: [
                         {'label':'Google Chrome', 'kind':'app', 'path':str(link), 'appid':None},
                         {'label':'Google Chrome', 'kind':'app', 'path':None, 'appid':'Chrome'},
                         {'label':'Chrome', 'kind':'app', 'path':str(executable), 'appid':None},
                     ])
    monkeypatch.setattr(launcher_api, 'resolver', lambda: local)
    monkeypatch.setattr(launcher_api, 'launcher_settings', lambda: {'enabled':True})
    opened = []
    monkeypatch.setattr(launcher_api, '_launch',
                        lambda candidate_id: opened.append(local.candidate(candidate_id)) or {'status':'opened'})
    for text in ('افتح جوجل كروم', 'افتح كروم', 'open Google Chrome'):
        reply = launcher_api.local_chat_launch([{'role':'user', 'content':text}])
        assert reply and 'فتحتلك' in reply
        assert opened[-1].args.get('appid') == 'Chrome'


def test_official_http_cpu_package_tree_beats_unsafe_board_temperatures():
    from core import hardware_sensors as hw
    tree = {
        'Version': '0.9.6', 'Text': 'Sensor', 'Children': [{
            'Text': 'computer', 'Children': [
                {'Text': 'Motherboard', 'HardwareId': '/lpc/0', 'Children': [
                    {'Text': 'Temperatures', 'Children': [
                        {'Type': 'Temperature', 'Text': 'CPU socket', 'SensorId': '/lpc/0/temperature/0',
                         'RawValue': '41.0 °C', 'Children': []}
                    ]}
                ]},
                {'Text': 'Intel Core i7', 'HardwareId': '/intelcpu/0', 'Children': [
                    {'Text': 'Temperatures', 'Children': [
                        {'Type': 'Temperature', 'Text': 'Core Max', 'SensorId': '/intelcpu/0/temperature/0',
                         'RawValue': '68.0 °C', 'Children': []},
                        {'Type': 'Temperature', 'Text': 'CPU Package', 'SensorId': '/intelcpu/0/temperature/1',
                         'RawValue': '64.0 °C', 'Children': []},
                        {'Type': 'Load', 'Text': 'CPU Total', 'SensorId': '/intelcpu/0/load/0',
                         'RawValue': 50.0, 'Children': []},
                    ]}
                ]}
            ]
        }]
    }
    records=hw._parse_http_sensor_tree(tree)
    measured=hw._collect_temperatures(records)
    assert measured['cpu_c']==64.0
    assert measured['cpu_sensor']=='CPU Package'
    assert measured['gpu_c'] is None
    assert len(records)==3


def test_official_http_raw_value_numeric_and_celsius_formats():
    from core import hardware_sensors as hw
    assert hw._http_temperature('64.0 °C') == 64.0
    assert hw._http_temperature('64,5 °C') == 64.5
    assert hw._http_temperature(66.2) == 66.2
    assert hw._http_temperature('62.1 °F') is None
    assert hw._http_temperature('not a sensor') is None
    assert hw._parse_http_sensor_tree({'Children': []}) == []


def test_local_lhm_http_reply_skips_wmi_and_dll(monkeypatch):
    from core import hardware_sensors as hw
    monkeypatch.setattr(hw, '_is_windows', lambda: True)
    monkeypatch.setattr(hw.shutil, 'which', lambda _: 'powershell.exe')
    monkeypatch.setattr(hw, '_read_local_http', lambda: {
        'cpu_c': 64.0, 'cpu_sensor': 'CPU Package',
        'gpu_c': None, 'storage_c': None, 'provider': 'LibreHardwareMonitor (local HTTP)',
    })
    def no_shell(*args, **kwargs):
        raise AssertionError('PowerShell should not start when LHM HTTP is already working')
    monkeypatch.setattr(hw, '_query_lhm', no_shell)
    monkeypatch.setattr(hw, '_query_local_library', no_shell)
    result=hw.read_local_temperatures()
    assert result['cpu_c']==64.0
    assert result['provider']=='LibreHardwareMonitor (local HTTP)'


def test_lhm_http_uses_only_fixed_loopback_and_does_not_use_proxy(monkeypatch):
    import json
    from core import hardware_sensors as hw
    sample={
        'Version':'0.9.6','Children':[{
            'HardwareId':'/intelcpu/0','Children':[{
                'Text':'Temperatures','Children':[{
                    'Type':'Temperature','Text':'CPU Package',
                    'SensorId':'/intelcpu/0/temperature/3',
                    'RawValue':64.0,'Children':[]
                }]
            }]
        }]
    }
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,size):return json.dumps(sample).encode('utf-8')
    class Opener:
        def open(self,req,timeout):
            assert req.full_url == 'http://127.0.0.1:8085/data.json'
            assert timeout <= 0.5
            return Response()
    monkeypatch.setattr(hw.urllib.request,'build_opener',lambda *args: Opener())
    monkeypatch.setattr(hw,'_http_reading',None)
    monkeypatch.setattr(hw,'_http_reading_at',0.)
    measured=hw._read_local_http()
    assert measured['cpu_c']==64.0
    assert measured['cpu_sensor']=='CPU Package'


def test_temperature_question_never_waits_for_sensor_installer(monkeypatch):
    from core import windows_facts, hardware_sensors as hw
    monkeypatch.setattr(windows_facts.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(hw,'snapshot',lambda **kwargs:{
        'cpu_c': None, 'reason':'monitor_not_installed',
    })
    monkeypatch.setattr(hw,'auto_setup_sensors',lambda:'started')
    def must_not_wait(*args, **kwargs):
        raise AssertionError('Do not block chat on sensor setup')
    monkeypatch.setattr(hw,'ensure_sensors_ready',must_not_wait)
    response=windows_facts.answer('درجة حرارة المعالج كام؟')
    assert 'الخلفية' in response and 'مفيش رقم موثوق' in response


def test_sensor_api_returns_only_measured_data(monkeypatch):
    from api_routes import openhub
    from core import hardware_sensors as hw
    monkeypatch.setattr(hw,'read_local_temperatures',lambda:{
        'cpu_c':64., 'cpu_sensor':'CPU Package',
        'provider':'LibreHardwareMonitor (local HTTP)', 'reason':None,
    })
    result=openhub.cpu_temperature()
    assert result['cpu_c']==64.
    assert result['cpu_sensor']=='CPU Package'
    assert 'installed_path' not in result


def test_chat_ui_uses_direct_temperature_route_and_keeps_multiquestion_guard():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'frontend/src/lib/chat.ts').read_text(encoding='utf-8')
    assert 'isStandaloneCpuTemperatureRequest(last.content)' in source
    assert "('/v1/openhub/cpu-temperature',{signal})" in source
    assert 'Further commands and second questions' in source


def test_elevated_lhm_gui_is_not_mistaken_for_missing_installation(monkeypatch):
    from core import hardware_sensors as hw
    monkeypatch.setattr(hw,'_is_windows',lambda:True)
    monkeypatch.setattr(hw.shutil,'which',lambda _: 'powershell.exe')
    monkeypatch.setattr(hw,'_read_local_http',lambda:None)
    monkeypatch.setattr(hw,'_query_lhm',lambda *_args,**_kwargs:None)
    monkeypatch.setattr(hw,'_monitor_executable',lambda:None)
    monkeypatch.setattr(hw,'_monitor_gui_running',lambda:True)
    reading=hw.read_local_temperatures()
    assert reading['cpu_c'] is None
    assert reading['reason']=='sensor_provider_unavailable'


def test_http_cpu_sensor_is_readable_even_without_powershell(monkeypatch):
    from core import hardware_sensors as hw
    monkeypatch.setattr(hw,'_is_windows',lambda:True)
    monkeypatch.setattr(hw.shutil,'which',lambda _:None)
    monkeypatch.setattr(hw,'_read_local_http',lambda:{
        'cpu_c':64.0,'cpu_sensor':'CPU Package','gpu_c':None,'storage_c':None,
        'provider':'LibreHardwareMonitor (local HTTP)',
    })
    reading=hw.read_local_temperatures()
    assert reading['cpu_c']==64.0
    assert reading['provider'].endswith('HTTP)')


def test_cpu_package_cannot_be_satisfied_by_motherboard_socket_or_gpu_package():
    from core import hardware_sensors as hw
    sensors=[
        {'Name':'CPU socket','Identifier':'/lpc/0/temperature/0','Parent':'/lpc/0','Value':49.},
        {'Name':'GPU Package','Identifier':'/gpu-nvidia/0/temperature/0','Parent':'/gpu-nvidia/0','Value':62.},
        {'Name':'CPU Package','Identifier':'/intelcpu/0/temperature/0','Parent':'/intelcpu/0','Value':64.},
    ]
    values=hw._collect_temperatures(sensors)
    assert values['cpu_c']==64.
    assert values['gpu_c']==62.
    only_board=hw._collect_temperatures(sensors[:2])
    assert only_board['cpu_c'] is None
