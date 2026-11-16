"""Sensor auto-recovery and speech continuity regression tests (offline)."""
from pathlib import Path
from types import SimpleNamespace
from core import hardware_sensors as hw
from core import windows_facts

ROOT = Path(__file__).resolve().parents[1]


def test_temp_query_starts_bundled_lhm_when_wmi_is_down(monkeypatch, tmp_path):
    monitor = tmp_path / 'hardware-monitor' / 'LibreHardwareMonitor.exe'
    monitor.parent.mkdir()
    monitor.write_bytes(b'fake-test-binary')
    monkeypatch.setattr(hw, '_is_windows', lambda: True)
    monkeypatch.setattr(hw.shutil, 'which', lambda name: 'powershell.exe')
    monkeypatch.setattr(hw, '_monitor_executable', lambda: monitor)
    started=[]
    monkeypatch.setattr(hw, '_last_start_attempt', 0.0)
    monkeypatch.setattr(hw.subprocess, 'Popen', lambda *args, **kwargs: started.append(args[0]))
    monkeypatch.setattr(hw.time, 'sleep', lambda _: None)
    responses=iter([None, '[{"Name":"CPU Package","Identifier":"/intelcpu/0/temperature/0","Value":66,"SensorType":"Temperature"}]'])
    monkeypatch.setattr(hw, '_query_lhm', lambda *a, **kw: next(responses))
    data=hw.read_local_temperatures()
    assert data['cpu_c']==66.0 and data['launched_local_provider']
    assert started==[[str(monitor)]]


def test_missing_monitor_repairs_and_reads_in_the_same_request(monkeypatch):
    monkeypatch.setattr(hw,'_is_windows', lambda: True)
    monkeypatch.setattr(hw.shutil,'which',lambda _: 'powershell.exe')
    monkeypatch.setattr(hw,'_monitor_executable',lambda: None)
    monkeypatch.setattr(hw,'_query_lhm',lambda *a,**kw: None)
    assert hw.read_local_temperatures()['reason']=='monitor_not_installed'
    monkeypatch.setattr(windows_facts.platform,'system',lambda:'Windows')
    readings=iter([{'cpu_c':None,'reason':'monitor_not_installed'},
                   {'cpu_c':63.7,'cpu_sensor':'CPU Package'}])
    monkeypatch.setattr(hw,'snapshot',lambda **kw:next(readings))
    monkeypatch.setattr(hw,'ensure_sensors_ready',lambda:'installed')
    assert '63.7' in windows_facts.answer('قيس درجة حرارة المعالج')


def test_sensor_setup_waits_for_the_shared_process(monkeypatch,tmp_path):
    import subprocess
    monitor=tmp_path/'LibreHardwareMonitor.exe'
    monkeypatch.setattr(hw,'auto_setup_sensors',lambda:'running')
    monkeypatch.setattr(hw,'_monitor_executable',lambda:monitor if monitor.exists() else None)
    def finish(timeout):
        assert timeout==1
        monitor.touch()
        return 0
    monkeypatch.setattr(hw,'_auto_setup_process',SimpleNamespace(wait=finish))
    assert hw.ensure_sensors_ready(timeout=1)=='installed'
    def stalled(timeout):
        raise subprocess.TimeoutExpired('install',timeout)
    monkeypatch.setattr(hw,'_auto_setup_process',SimpleNamespace(wait=stalled))
    assert hw.ensure_sensors_ready(timeout=1)=='timeout'


def test_failed_provider_never_fabricates_temperature(monkeypatch, tmp_path):
    m=tmp_path/'LibreHardwareMonitor.exe';m.write_bytes(b'test')
    monkeypatch.setattr(hw,'_is_windows',lambda:True)
    monkeypatch.setattr(hw.shutil,'which',lambda _: 'powershell.exe')
    monkeypatch.setattr(hw,'_monitor_executable',lambda:m)
    monkeypatch.setattr(hw,'_start_installed_monitor',lambda _:True)
    monkeypatch.setattr(hw.time,'sleep',lambda _:None)
    monkeypatch.setattr(hw,'_query_lhm',lambda *a,**kw:None)
    reading=hw.read_local_temperatures()
    assert reading['cpu_c'] is None and reading['reason']=='sensor_provider_unavailable'


def test_speech_playback_never_discards_queued_audio_on_normal_lag():
    code=(ROOT/'frontend/src/lib/liveVoice.ts').read_text(encoding='utf-8')
    interval=code.split('const queuedSeconds=Math.max(',1)[1].split('let raw:string;',1)[0]
    assert 'this.clearAudio()' not in interval
    assert 'this.next+=buffer.duration' in code
    assert 'socket.bufferedAmount>1000000' in code
    assert 'this.fail(' in code.split('if(socket.bufferedAmount>1000000)',1)[1].split('const level=',1)[0]


def test_installer_provides_repair_and_checked_sensor_option():
    assert (ROOT/'INSTALL_BARQ_SENSORS.bat').exists()
    for name in ('installer.iss','installer_update.iss'):
        source=(ROOT/'scripts'/name).read_text(encoding='utf-8')
        task=next(line for line in source.splitlines() if line.startswith('Name: hardwaresensors;'))
        assert 'unchecked' not in task
        assert 'INSTALL_BARQ_SENSORS.bat' in source
