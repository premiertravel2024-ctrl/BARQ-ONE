"""Gemini voice services: recorded voice -> transcription, text -> Egyptian male speech.

Uses official REST APIs. API keys remain on the local Python backend. No device
control is given to the model by this module.
"""
from __future__ import annotations

import base64
import os
from typing import Any
from urllib.parse import urlsplit

import httpx

BASE = "https://generativelanguage.googleapis.com"
ALLOWED_MIMES = {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/mpeg", "audio/mp3", "audio/aac", "audio/opus"}
MALE_VOICES = {"Charon": "هادئ واحترافي", "Achird": "ودود وطبيعي", "Orus": "عميق وواثق", "Puck": "حيوي", "Algieba": "ناعم", "Fenrir": "حماسي"}
TTS_MODELS = {"gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"}
TRANSCRIBE_MODEL = "gemini-3.5-transcribe"
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_SPEECH_CHARS = 1800

class VoiceError(Exception):
    pass

def gemini_key() -> str:
    from core.secrets import get
    return get('GEMINI_API_KEY').strip()

def require_key() -> str:
    key = gemini_key()
    if not key:
        raise VoiceError("أضف GEMINI_API_KEY إلى ملف .env لتفعيل صوت Gemini.")
    if os.getenv("LOCAL_ONLY", "false").strip().lower() in ("1", "true", "yes"):
        raise VoiceError("وضع LOCAL_ONLY يمنع إرسال الصوت إلى Gemini.")
    return key

def validate_audio(blob: bytes, mime: str) -> str:
    normalized = mime.lower().split(";", 1)[0].strip()
    if normalized not in ALLOWED_MIMES:
        raise VoiceError("صيغة الصوت غير مدعومة. استخدم تسجيل WebM أو WAV أو MP4.")
    if not blob:
        raise VoiceError("لم يصل تسجيل صوتي.")
    if len(blob) > MAX_AUDIO_BYTES:
        raise VoiceError("التسجيل كبير. الحد الأقصى 8 ميجابايت.")
    return normalized

def _raise_gemini(response: httpx.Response):
    if response.status_code >= 400:
        # Never surface key or whole upstream payload.
        if response.status_code == 429:
            raise VoiceError("حصة Gemini المجانية للصوت انتهت مؤقتًا؛ جرّب لاحقًا.")
        if response.status_code in (401, 403):
            raise VoiceError("مفتاح Gemini غير صالح أو لا يملك صلاحية النموذج الصوتي.")
        if response.status_code == 404:
            raise VoiceError("النموذج الصوتي غير متاح لهذا المفتاح. راجع إعدادات Google AI Studio.")
        raise VoiceError(f"فشل اتصال Gemini (HTTP {response.status_code}).")

def extract_text(body: dict[str, Any]) -> str:
    """Parse Interactions REST output and legacy candidates without exposing metadata."""
    output=body.get('output_text')
    if isinstance(output,str) and output.strip():
        return output.strip()
    for step in reversed(body.get('steps') or []):
        if not isinstance(step,dict) or step.get('type')!='model_output':
            continue
        chunks=[part.get('text','').strip() for part in step.get('content') or []
                if isinstance(part,dict) and part.get('type')=='text' and isinstance(part.get('text'),str)]
        if any(chunks):
            return ' '.join(filter(None,chunks))
    chunks=[]
    for choice in body.get('candidates', []):
        for part in (choice.get('content') or {}).get('parts', []):
            if isinstance(part.get('text'),str):
                chunks.append(part['text'].strip())
    result=' '.join(filter(None,chunks))
    if not result:
        raise VoiceError('Gemini رجّع نتيجة من غير كلام. جرّب تسجيل أوضح أو فعّل نموذج التعرف المحلي.')
    return result

def extract_audio(body: dict[str, Any]) -> tuple[bytes,str]:
    for choice in body.get("candidates", []):
        for part in (choice.get("content") or {}).get("parts", []):
            audio=part.get("inlineData") or part.get("inline_data") or {}
            if audio.get("data"):
                try:
                    data=base64.b64decode(audio["data"],validate=True)
                except (ValueError, TypeError) as exc:
                    raise VoiceError("وصل رد صوتي تالف من Gemini.") from exc
                if not data:
                    raise VoiceError("ملف الصوت الناتج فارغ.")
                return data, str(audio.get("mimeType") or audio.get("mime_type") or "audio/wav")
    raise VoiceError("Gemini لم يرجع صوتًا. جرّب نموذج TTS الآخر.")

async def transcribe_audio(blob: bytes, mime: str) -> str:
    """Files API -> Gemini Transcribe Interactions API; opt-in offline fallback.

    Never silently downloads models, never logs audio, deletes remote temp uploads.
    """
    mime=validate_audio(blob,mime)
    from voice.offline import transcribe_local
    local_only=os.getenv('LOCAL_ONLY','false').strip().lower() in ('1','true','yes')
    key=gemini_key()
    if local_only or not key:
        try:
            fallback=await transcribe_local(blob)
        except Exception as exc:
            raise VoiceError('المحرك المحلي مش قادر يفهم التسجيل. تأكد من نموذج Whisper المحلي وصيغة الصوت.') from exc
        if fallback:return fallback
        if local_only:
            raise VoiceError('وضع LOCAL_ONLY شغّال، ومفيش محرك تحويل محلي مجهز. ثبّت faster-whisper واضبط BARQ_LOCAL_STT_MODEL_PATH.')
        require_key()  # raises user-facing error for unconfigured Gemini
        raise VoiceError("التعرف على الصوت غير مجهز.")
    headers={'x-goog-api-key':key}
    file_name=None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(75.0,connect=12.0)) as client:
            try:
                init=await client.post(
                    BASE+'/upload/v1beta/files',
                    headers={**headers,'X-Goog-Upload-Protocol':'resumable','X-Goog-Upload-Command':'start',
                        'X-Goog-Upload-Header-Content-Length':str(len(blob)),
                        'X-Goog-Upload-Header-Content-Type':mime},
                    json={'file':{'display_name':'BARQ voice message'}},
                )
                _raise_gemini(init)
                upload_url=init.headers.get('x-goog-upload-url','')
                target=urlsplit(upload_url)
                if target.scheme!='https' or target.hostname!='generativelanguage.googleapis.com':
                    raise VoiceError('Gemini لم يرجع رابط رفع آمنًا.')
                uploaded=await client.post(upload_url,content=blob,headers={
                    'X-Goog-Upload-Offset':'0', 'X-Goog-Upload-Command':'upload, finalize', 'Content-Type':mime,
                })
                _raise_gemini(uploaded)
                file_info=uploaded.json().get('file') or {}
                file_name=file_info.get('name')
                file_uri=file_info.get('uri')
                if not isinstance(file_uri,str) or not file_uri.startswith('https://generativelanguage.googleapis.com/'):
                    raise VoiceError('Gemini لم يؤكد رفع الملف الصوتي.')
                # Model-specific endpoint: Gemini 3.5 Transcribe uses Interactions, NOT generateContent.
                # Leave language unset to recognize Egyptian Arabic mixed with English commands.
                payload={'model':TRANSCRIBE_MODEL,'input':[{'type':'audio','uri':file_uri,'mime_type':mime}]}
                response=await client.post(BASE+'/v1beta/interactions',headers=headers,json=payload)
                _raise_gemini(response)
                return extract_text(response.json())
            finally:
                if isinstance(file_name,str) and file_name.startswith('files/') and len(file_name)<120:
                    try:await client.delete(BASE+'/v1beta/'+file_name,headers=headers,timeout=5)
                    except httpx.HTTPError:pass
    except (VoiceError,httpx.HTTPError,ValueError) as exc:
        try:
            fallback=await transcribe_local(blob)
        except Exception:
            fallback=None
        if fallback:return fallback
        if isinstance(exc,VoiceError):raise
        raise VoiceError('الاتصال بخدمة الصوت فشل. راجع الإنترنت، أو فعّل Whisper المحلي كبديل.') from exc

def extract_interaction_audio(body: dict[str, Any]) -> tuple[bytes,str]:
    """Extract the latest audio block from the documented Gemini Interactions response.

    Unlike generateContent, Interactions produces steps[].content[] audio blocks.
    """
    for step in reversed(body.get('steps') or []):
        if step.get('type') != 'model_output':
            continue
        for part in reversed(step.get('content') or []):
            if part.get('type') != 'audio' or not part.get('data'):
                continue
            try:
                audio=base64.b64decode(part['data'],validate=True)
            except (ValueError,TypeError) as exc:
                raise VoiceError('وصل رد صوتي تالف من Gemini.') from exc
            if not audio:
                raise VoiceError('ملف الصوت الناتج فارغ.')
            return audio,'audio/wav'
    raise VoiceError('Gemini لم يرجع صوتًا. جرّب نموذج TTS الآخر.')

async def synthesize_speech(text: str, voice: str='Charon', model: str='gemini-3.8-flash-lite-tts') -> tuple[bytes,str]:
    key=require_key()
    text=text.strip()
    if not text or len(text)>MAX_SPEECH_CHARS:
        raise VoiceError(f'نص الرد الصوتي لازم يكون من 1 إلى {MAX_SPEECH_CHARS} حرف.')
    if voice not in MALE_VOICES or model not in TTS_MODELS:
        raise VoiceError('الصوت الرجالي أو نموذج Gemini غير مدعوم.')
    # Gemini 3.8 Flash / Flash-Lite TTS now use v1beta/interactions.
    # Never put delivery directions into spoken text: use annotations instead.
    payload={
        'model':model,
        'input':[{'type':'user_input','content':[{
            'type':'text','text':text,
            'annotations':[{'type':'speech_metadata','style':
                'Natural adult male from Cairo speaking authentic colloquial Egyptian Arabic, '
                'warm and conversational with relaxed pacing, correct Egyptian vowels, '
                'natural pauses; not Modern Standard Arabic or a newsreader.'}]
        }]}],
        'response_format':{'type':'audio'},
        'generation_config':{'speech_config':[{'voice':voice}]}
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0,connect=12.0)) as client:
            response=await client.post(BASE+'/v1beta/interactions',
                headers={'x-goog-api-key':key},json=payload)
            _raise_gemini(response)
            audio,mime=extract_interaction_audio(response.json())
    except (httpx.HTTPError,ValueError) as exc:
        if isinstance(exc,VoiceError):raise
        raise VoiceError('تعذر توليد الصوت من Gemini.') from exc
    if len(audio)<44 or audio[:4]!=b'RIFF' or audio[8:12]!=b'WAVE':
        raise VoiceError('ملف WAV من Gemini غير صالح.')
    return audio,mime
