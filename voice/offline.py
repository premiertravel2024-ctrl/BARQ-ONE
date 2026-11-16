"""Explicit opt-in local STT fallback. Never downloads a model automatically."""
from __future__ import annotations
import asyncio
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import importlib.util
import os


def model_directory():
    """Honor explicit environment override, then local user-selected model folder."""
    from core.paths import state_file
    setting=state_file('voice_stt_path.txt')
    return os.getenv('BARQ_LOCAL_STT_MODEL_PATH','').strip() or (setting.read_text(encoding='utf-8').strip() if setting.is_file() else '')


def local_stt_ready() -> bool:
    root=model_directory()
    return bool(root and Path(root).is_dir() and importlib.util.find_spec('faster_whisper'))

@lru_cache(maxsize=2)
def _load_model(folder: str):
    from faster_whisper import WhisperModel
    return WhisperModel(folder, device='cpu', compute_type='int8', local_files_only=True)


def _decode_audio(blob: bytes, folder: str) -> str:
    model=_load_model(folder)
    segments,_=model.transcribe(BytesIO(blob), beam_size=3, vad_filter=True)
    return ' '.join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


async def transcribe_local(blob: bytes) -> str | None:
    if not local_stt_ready():
        return None
    folder=model_directory()
    return await asyncio.to_thread(_decode_audio,blob,folder)
