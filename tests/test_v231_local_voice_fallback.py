import pytest
from voice.local_speaker import local_audio_command,synthesize_sapi
from voice.brain_bridge import BARQVoiceBrain


@pytest.mark.asyncio
async def test_local_audio_uses_same_policy_grounded_brain():
    calls=[]
    async def fake_dispatch(name,args,chat):
        calls.append((name,args))
        return {'status':'opened','message':'اتفتحت المفكرة.'}
    async def fake_transcribe(data):return 'يا برق افتح المفكرة'
    result=await local_audio_command(b'0'*400,brain=BARQVoiceBrain(dispatcher=fake_dispatch),
            transcriber=fake_transcribe,computer_enabled=True)
    assert result['status']=='opened' and calls[0][0]=='open_on_computer'
    assert result['transcript']=='يا برق افتح المفكرة'


@pytest.mark.asyncio
async def test_local_voice_refuses_without_stt_and_wont_run_tools():
    async def empty(_:bytes):return None
    result=await local_audio_command(b'1'*400,transcriber=empty,computer_enabled=True)
    assert result['status']=='stt_unavailable'


def test_sapi_rejects_invalid_text_even_when_not_on_windows():
    with pytest.raises(ValueError):synthesize_sapi('')
    with pytest.raises(ValueError):synthesize_sapi('x'*500)


@pytest.mark.asyncio
async def test_disconnected_local_voice_does_not_execute_a_completed_transcript():
    async def transcribe(_):
        return 'افتح المفكرة'

    async def disconnected():
        return True

    async def dispatch(*_):
        pytest.fail('A cancelled voice request reached a desktop tool')

    result = await local_audio_command(
        b'0' * 400, brain=BARQVoiceBrain(dispatcher=dispatch),
        transcriber=transcribe, computer_enabled=True, disconnected=disconnected,
    )
    assert result['status'] == 'cancelled'
