"""Regressions for low-latency voice backlog, without Google credentials or microphone."""
import asyncio
from voice.live import BoundedLiveAudioUplink


def test_older_audio_evicted_when_network_is_slower_than_microphone():
    async def check():
        q=BoundedLiveAudioUplink(limit=3)
        for i in range(10):
            assert q.audio(bytes([i]))
        assert q.dropped==7
        assert [await q.get() for _ in range(3)]==[
            ('audio',b'\x07'),('audio',b'\x08'),('audio',b'\x09')]
    asyncio.run(check())


def test_utterance_boundaries_never_get_lost_when_queue_is_full():
    async def check():
        q=BoundedLiveAudioUplink(limit=3)
        q.audio(b'older-1')
        q.end_utterance()
        q.audio(b'older-2')
        q.end_utterance()
        # Both explicit end markers survive and remain ordered. Only old
        # audio frames may be discarded to bound latency.
        assert [await q.get() for _ in range(3)]==[
            ('end',None),('audio',b'older-2'),('end',None)]
        assert q.dropped==1
    asyncio.run(check())


def test_control_only_full_queue_drops_audio_but_never_control():
    async def check():
        q=BoundedLiveAudioUplink(limit=2)
        q.end_utterance()
        q.end_utterance()
        assert not q.audio(b'sound')
        assert q.dropped==1
        try:
            q.end_utterance()
            assert False,'control queue should fail closed'
        except RuntimeError:
            pass
        assert [await q.get() for _ in range(2)]==[('end',None),('end',None)]
    asyncio.run(check())


def test_empty_buffer_waits_without_busy_loop():
    async def check():
        q=BoundedLiveAudioUplink(limit=3)
        consumer=asyncio.create_task(q.get())
        await asyncio.sleep(0)
        assert not consumer.done()
        q.audio(b'new')
        assert await asyncio.wait_for(consumer,timeout=1)==('audio',b'new')
    asyncio.run(check())


def test_sdk_initialization_failure_reports_error_instead_of_silent_disconnect(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from voice import live
    monkeypatch.delenv('LOCAL_ONLY',raising=False)
    monkeypatch.setattr(live,'gemini_key',lambda:'fake-for-test-only')
    google=ModuleType('google')
    genai=ModuleType('google.genai')
    genai.types=SimpleNamespace()
    def fail(**kw):raise RuntimeError('SDK failed during startup')
    genai.Client=fail
    google.genai=genai
    with monkeypatch.context() as mp:
        mp.setitem(sys.modules,'google',google)
        mp.setitem(sys.modules,'google.genai',genai)
        app=FastAPI();app.websocket('/voice')(live.handle_live)
        with TestClient(app).websocket_connect('/voice') as socket:
            event=socket.receive_json()
            assert event['type']=='error'
            assert event['code']=='live_unavailable'
            assert 'SDK failed during startup' not in event['message']


def test_release_preflight_checks_worklet_and_update_integration(tmp_path):
    from scripts.audit_release_readiness import audit
    import shutil
    root=__import__('pathlib').Path(__file__).resolve().parents[1]
    # No real installer needed to prove missing artifacts are rejected.
    assert audit(root)['status']=='ok'
    # Missing source should fail clearly before building a Windows EXE.
    assert audit(tmp_path)['status']=='failed'
