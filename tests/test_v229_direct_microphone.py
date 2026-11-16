"""Regression gates for in-process BARQ microphone capture."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import threading
import time


def test_wake_model_local_or_existing_legacy(monkeypatch, tmp_path):
    from voice import direct_wake
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    monkeypatch.setattr(direct_wake, '__file__', str(tmp_path / 'voice' / 'direct_wake.py'))
    model = tmp_path / 'models' / 'wake' / direct_wake.MODEL_NAME
    (model / 'am').mkdir(parents=True)
    (model / 'conf').mkdir()
    assert direct_wake.model_path() == model


def test_native_direct_mic_status_and_rapid_wake(monkeypatch, tmp_path):
    from voice import direct_wake
    model = tmp_path / 'model'; model.mkdir()
    monkeypatch.setattr(direct_wake, 'model_path', lambda: model)
    seen = []
    def triggered():
        seen.append('heard'); direct.stop_event.set()
    direct = direct_wake.DirectWake(triggered, lambda: False, lambda: None)
    # Do not read a real user's saved wake fingerprint: that deliberately
    # disables transcript-only wake and previously hung this finite fake mic.
    monkeypatch.setattr(direct, '_templates_path', lambda: tmp_path / 'no-user-profile.npz')
    class FakeRec:
        def __init__(self, *args):pass
        def AcceptWaveform(self, data):return False
        def PartialResult(self):return json.dumps({'partial':'يا برء افتح'},ensure_ascii=False)
    class Stream:
        def __init__(self, **kwargs):self.callback=kwargs['callback']
        def __enter__(self):
            for _ in range(4):self.callback(b'\x00\x18' * 4000,4000,None,None)
            return self
        def __exit__(self, *args):pass
    def query_devices(device=None,kind=None):
        return {'name':'USB microphone','default_samplerate':16000} if kind=='input' else [{'max_input_channels':1,'name':'USB microphone'}]
    monkeypatch.setitem(sys.modules,'sounddevice',SimpleNamespace(query_devices=query_devices,RawInputStream=Stream))
    monkeypatch.setitem(sys.modules,'vosk',SimpleNamespace(SetLogLevel=lambda _:None,Model=lambda _:object(),KaldiRecognizer=FakeRec))
    monkeypatch.setitem(sys.modules,'audioop',SimpleNamespace(ratecv=lambda data,*args:(data,None)))
    worker = threading.Thread(target=direct._run, daemon=True, name='direct-wake-test')
    worker.start()
    worker.join(timeout=3)
    if worker.is_alive():
        direct.stop_event.set()
        worker.join(timeout=2)
    assert not worker.is_alive(), 'Fake microphone must not wait forever for more frames'
    assert seen == ['heard']
    result = direct.status()
    assert result['engine']=='direct'
    assert result['last_recognized']=='يا برء افتح'
    assert result['last_wake']>0
    assert 'audio' not in result and 'recording' not in result


def test_direct_listener_selected_without_companion(monkeypatch):
    from voice import wake
    monkeypatch.setattr(wake, 'wake_executable', lambda: None)
    monkeypatch.setattr(wake, 'native_dependencies_present', lambda:True)
    monkeypatch.setattr(wake, 'model_path', lambda: Path('fake'))
    monkeypatch.setattr(wake, 'retire_legacy_listeners', lambda:(True,''))
    monkeypatch.setattr(wake._direct_listener, 'start', lambda:(True,'starting'))
    monkeypatch.setattr(wake, '_companion', None)
    assert wake.start_listener() == (True,'starting')


def test_build_bundles_microphone_in_main_exe():
    script=(Path(__file__).resolve().parents[1] / 'scripts' / 'build_windows.ps1').read_text(encoding='utf8')
    main=script.index("'--name', 'BARQ'")
    helper=script.index("'--name', 'BARQ_Wake'")
    assert "'--collect-all', 'vosk', '--collect-all', 'sounddevice'" in script[main:helper]
    assert 'direct microphone runtime into BARQ desktop' in script


def test_saved_user_profile_cannot_change_fake_microphone_test(monkeypatch, tmp_path):
    """Simulate the real Windows AppData profile that caused the 90s timeout."""
    from voice import direct_wake, wake_fingerprint
    import numpy as np

    # A previously enrolled device should NOT alter an unrelated unit test.
    saved = tmp_path / 'real-user' / 'wake_acoustic_profile.npz'
    wake_fingerprint.save(saved, [np.zeros((36, 13), dtype='float32')] * 3)
    assert len(wake_fingerprint.load(saved)) == 3
    # The speech-recognition test always supplies its own empty profile path.
    isolated = tmp_path / 'fake-unenrolled-profile.npz'
    listener = direct_wake.DirectWake(lambda: None, lambda: False, lambda: None)
    monkeypatch.setattr(listener, '_templates_path', lambda: isolated)
    assert wake_fingerprint.load(listener._templates_path()) == []
    assert listener.has_profile() is False


def test_direct_mic_reconnects_after_callback_stalls(monkeypatch, tmp_path):
    """A dead input device should be reopened, not block forever on Queue.get."""
    from voice import direct_wake
    listener = direct_wake.DirectWake(lambda: None, lambda: False, lambda: None)
    monkeypatch.setattr(listener, '_templates_path', lambda: tmp_path / 'empty.npz')
    monkeypatch.setattr(direct_wake, 'model_path', lambda: tmp_path)
    monkeypatch.setattr(direct_wake, 'INPUT_IDLE_RESTART_SECONDS', 0.35)
    monkeypatch.setattr(direct_wake, 'INPUT_RETRY_DELAY_SECONDS', 0.01)
    class Recognizer:
        def __init__(self, *args): pass
    opened = []
    class SilentStream:
        def __init__(self, **kwargs): pass
        def __enter__(self):
            opened.append('opened')
            if len(opened) == 2:
                listener.stop_event.set()
            return self
        def __exit__(self, *args): pass
    sd = SimpleNamespace(
        query_devices=lambda device=None, kind=None: (
            {'name': 'Test mic', 'default_samplerate': 16000} if kind
            else [{'name': 'Test mic', 'max_input_channels': 1}]),
        RawInputStream=SilentStream)
    monkeypatch.setitem(sys.modules, 'sounddevice', sd)
    monkeypatch.setitem(sys.modules, 'vosk', SimpleNamespace(
        SetLogLevel=lambda _: None, Model=lambda _: object(), KaldiRecognizer=Recognizer))
    monkeypatch.setitem(sys.modules, 'audioop', SimpleNamespace(ratecv=lambda pcm, *args: (pcm, None)))
    worker = threading.Thread(target=listener._run, daemon=True)
    worker.start()
    worker.join(timeout=3)
    if worker.is_alive():
        listener.stop_event.set()
        worker.join(timeout=1)
    assert not worker.is_alive(), 'Reconnection must be interruptible'
    assert len(opened) >= 2, 'Unresponsive microphone should be reopened'
    assert listener.status()['state'] == 'stopped'
