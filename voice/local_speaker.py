"""Optional Windows SAPI speech output; no Google call, key or new package.

Experimental fallback for short local replies. SAPI may not have an Egyptian or
Arabic voice installed; do not claim otherwise. No shell=True or untrusted code.
"""
from __future__ import annotations
import base64
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voice.brain_bridge import BARQVoiceBrain


def synthesize_sapi(text:str,*,runner=subprocess.run,arabic_only:bool=False)->bytes:
    if not isinstance(text,str) or not (1<=len(text.strip())<=320) or any(c=='\x00' for c in text):
        raise ValueError('Local speech text invalid')
    if sys.platform!='win32':raise RuntimeError('Windows SAPI is only available on Windows')
    with tempfile.TemporaryDirectory(prefix='barq-sapi-') as root:
        wavefile=Path(root)/'voice.wav'
        # Base64-encoded text/path are DATA to a fixed script, never script code.
        payload=base64.b64encode(text.encode('utf-8')).decode('ascii')
        output=base64.b64encode(str(wavefile).encode('utf-8')).decode('ascii')
        script=(
            "Add-Type -AssemblyName System.Speech; "
            "$text=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+payload+"')); "
            "$path=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+output+"')); "
            "$voice=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "try {$voice.SetOutputToWaveFile($path); $voice.Speak($text)} "
            "finally {$voice.Dispose()}"
        )
        if arabic_only:
            select_arabic = (
                "$arabic=@($voice.GetInstalledVoices() | Where-Object "
                "{$_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'ar'} | "
                "Sort-Object -Property @{Expression={$_.VoiceInfo.Culture.Name -eq 'ar-EG'};Descending=$true},"
                "@{Expression={$_.VoiceInfo.Gender -eq 'Male'};Descending=$true}); "
                "if (-not $arabic.Count) {$voice.Dispose();exit 2}; "
                "$voice.SelectVoice($arabic[0].VoiceInfo.Name); "
            )
            script=script.replace("try {$voice.SetOutputToWaveFile",
                                  select_arabic+"try {$voice.SetOutputToWaveFile")
        cmd=base64.b64encode(script.encode('utf-16le')).decode('ascii')
        proc=runner(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',cmd],
                    capture_output=True,timeout=28,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),
                    shell=False)
        if proc.returncode!=0 or not wavefile.is_file():
            raise RuntimeError('Windows SAPI unavailable or voice synthesis failed')
        audio=wavefile.read_bytes()
        if len(audio)>8_000_000 or not audio.startswith(b'RIFF'):
            raise RuntimeError('Invalid SAPI audio response')
        return audio


_local_brains: dict[tuple[str,str],tuple[float,BARQVoiceBrain]]={}


def local_session_brain(session_id: str, conversation_id: str) -> BARQVoiceBrain:
    from voice.brain_bridge import BARQVoiceBrain

    now=time.monotonic()
    for key,(seen,_) in list(_local_brains.items()):
        if now-seen>180:del _local_brains[key]
    key=(session_id,conversation_id)
    entry=_local_brains.pop(key,None)
    brain=entry[1] if entry else BARQVoiceBrain()
    if len(_local_brains)>=16:del _local_brains[next(iter(_local_brains))]
    _local_brains[key]=(now,brain)
    return brain


async def local_audio_command(blob:bytes,*,brain=None,transcriber=None,
                              computer_enabled:bool|None=None,conversation_id:str='',
                              disconnected:Callable[[],Awaitable[bool]]|None=None, session_id:str='')->dict:
    """Local ASR -> same BARQ brain; no remote models, mic must be stopped first."""
    if not isinstance(blob,(bytes,bytearray)) or not 200 <= len(blob) <= 8_000_000:
        return {'status':'invalid_audio','spoken_ar':'التسجيل قصير أو أكبر من المسموح.','cards':[], 'needs_approval':False,'task_id':None}
    started=time.monotonic()
    if transcriber is None:
        from voice.offline import transcribe_local
        transcriber=transcribe_local
    try:spoken=await transcriber(bytes(blob))
    except (OSError,RuntimeError,ValueError):spoken=None
    if not spoken:
        return {'status':'stt_unavailable','spoken_ar':'التفريغ المحلي مش جاهز؛ ثبت نموذج Whisper المحلي الأول.','cards':[], 'needs_approval':False,'task_id':None}
    if brain is None:
        from voice.brain_bridge import BARQVoiceBrain
        brain=local_session_brain(session_id,conversation_id) if session_id else BARQVoiceBrain()
    if computer_enabled is None:
        from voice.wake import wake_preferences
        from computer_control.api import load_policy
        computer_enabled=bool(wake_preferences()['wake_computer_enabled'] and load_policy().enabled)
    if disconnected is not None and await disconnected():
        return {'status':'cancelled','spoken_ar':'وقفت الصوت قبل تنفيذ الأمر.','cards':[],
                'needs_approval':False,'task_id':None}
    from voice.command_guard import VoiceCommandGate
    gate=VoiceCommandGate();gate.record(spoken)
    dispatch_started=time.monotonic()
    result=await brain.ask(gate,{},computer_enabled=bool(computer_enabled),conversation_id=conversation_id)
    return {'transcript':spoken[:420],'dispatch_ms':round((dispatch_started-started)*1000),**result}


def speaker_mode()->str:
    from core.paths import state_file
    try:
        selected=state_file('voice_speaker.txt').read_text(encoding='utf-8').strip()
    except (OSError,ValueError):selected='gemini'
    return selected if selected in ('gemini','local') else 'gemini'


def set_speaker_mode(value:str)->str:
    if value not in ('gemini','local'):
        raise ValueError('Unknown voice speaker mode')
    from core.paths import state_file
    path=state_file('voice_speaker.txt')
    temporary=path.with_suffix('.tmp')
    temporary.write_text(value,encoding='utf-8')
    temporary.replace(path)
    return value
