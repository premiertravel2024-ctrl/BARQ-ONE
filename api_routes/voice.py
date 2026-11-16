"""Local voice routes service. HTTP API contracts remain in api.py."""
import os
from pathlib import Path
from fastapi import HTTPException, Response
from core.paths import state_file
from voice.offline import local_stt_ready, model_directory
from voice.gemini import (
    gemini_key, MALE_VOICES, TTS_MODELS, MAX_AUDIO_BYTES,
    MAX_SPEECH_CHARS, VoiceError, transcribe_audio, synthesize_speech,
)


def voice_config():
    local_ready=local_stt_ready()
    cloud_allowed=os.getenv('LOCAL_ONLY','false').strip().lower() not in ('1','true','yes')
    return {
        'configured':(bool(gemini_key()) and cloud_allowed) or local_ready,
        'tts_configured':bool(gemini_key()) and cloud_allowed,
        'live_configured':bool(gemini_key()) and cloud_allowed,
        'live_model':__import__('voice.live',fromlist=['LIVE_MODEL']).LIVE_MODEL,
        'local_stt_ready':local_ready,
        'local_stt_model_path':model_directory(),
        'voices':[{'id':key,'description':description} for key,description in MALE_VOICES.items()],
        'tts_models':sorted(TTS_MODELS),
        'speaker':__import__('voice.local_speaker',fromlist=['speaker_mode']).speaker_mode(),
        'stt_model':'gemini-3.5-transcribe',
        'max_audio_bytes':MAX_AUDIO_BYTES,
        'max_speech_chars':MAX_SPEECH_CHARS,
    }


def save_voice_model_path(path):
    chosen=path.strip()
    if chosen and (not Path(chosen).is_absolute() or not Path(chosen).is_dir()):
        raise HTTPException(400,'اختار مجلد نموذج Whisper محلي موجود بالفعل.')
    state_file('voice_stt_path.txt').write_text(chosen,encoding='utf-8')
    return {'saved':True,'local_stt_ready':local_stt_ready()}


async def transcribe_request(req):
    if req.headers.get('content-length') and int(req.headers['content-length'])>MAX_AUDIO_BYTES:
        raise HTTPException(413,'التسجيل أكبر من الحجم المسموح.')
    data=bytearray()
    async for part in req.stream():
        data.extend(part)
        if len(data)>MAX_AUDIO_BYTES:
            raise HTTPException(413,'التسجيل أكبر من الحجم المسموح.')
    try:
        text=await transcribe_audio(bytes(data),req.headers.get('content-type',''))
    except VoiceError as exc:
        raise HTTPException(400,str(exc)) from exc
    return {'text':text}


async def speak_request(req):
    try:
        audio,mime=await synthesize_speech(req.text,req.voice,req.model)
    except VoiceError as exc:
        raise HTTPException(400,str(exc)) from exc
    return Response(content=audio,media_type=mime,headers={'Cache-Control':'no-store'})
