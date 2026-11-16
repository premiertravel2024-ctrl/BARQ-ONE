"""Direct Windows microphone wake detection INSIDE the BARQ desktop process.

No helper executable, HTTP loopback, or second mutex. Captures raw PCM via
PortAudio/sounddevice, processes it locally with installed Vosk Arabic model,
keeps only short-lived diagnostic text in memory, and releases the microphone
whenever the Gemini Live session is running.
"""
from __future__ import annotations

import json
import math
import queue
import sys
import threading
import time
from array import array
import re
from pathlib import Path
from typing import Callable
from voice import wake_fingerprint


MODEL_NAME = 'vosk-model-ar-mgb2-0.4'
WAKE_WORDS = ['يا برق', 'يا برء', 'يا برأ', 'يا برك', 'برق', 'برء', 'برك', '[unk]']
# An active PortAudio stream must deliver frames, even during silence. If the
# callback stops, reset the stream instead of waiting on an empty queue forever.
INPUT_IDLE_RESTART_SECONDS = 5.0
INPUT_RETRY_DELAY_SECONDS = 0.5


def model_path() -> Path | None:
    from core.paths import state_file
    app_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    for path in (app_dir / 'models' / 'wake' / MODEL_NAME,
                 state_file('wake_models') / MODEL_NAME):
        if (path / 'am').is_dir() and (path / 'conf').is_dir():
            return path
    return None


def native_dependencies_present() -> bool:
    """Probe lazily so ordinary server imports and non-Windows tests still work."""
    try:
        import sounddevice  # noqa: F401
        import vosk  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


def voice_level(pcm: bytes) -> int:
    """RMS loudness only. No raw audio/transcripts written to disk."""
    if not pcm:
        return 0
    samples = array('h')
    samples.frombytes(pcm[:len(pcm) - len(pcm) % 2])
    if not samples:
        return 0
    mean = sum(int(sample) * int(sample) for sample in samples) / len(samples)
    return min(100, round(math.sqrt(mean) * 600 / 32768))


def create_recognizer(model, vosk):
    """Use a small phrase grammar when supported; some graphs are precompiled."""
    try:
        return vosk.KaldiRecognizer(model, 16000, json.dumps(WAKE_WORDS, ensure_ascii=False))
    except (TypeError, ValueError, RuntimeError):
        return vosk.KaldiRecognizer(model, 16000)


class DirectWake:
    def __init__(self, on_wake: Callable[[], None], live_active: Callable[[], bool],
                 device_preference: Callable[[], int | None]):
        self.on_wake = on_wake
        self.live_active = live_active
        self.device_preference = device_preference
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self._profile_cache_stamp = None
        self._profile_cache_ready = False
        self._owner_samples=[]
        self._enrolling: list = []
        self._enrollment_active = False
        self._details: dict = {
            'state': 'stopped', 'detail': '', 'level': 0,
            'audio_seen': False, 'heard_speech': False, 'last_audio_at': 0,
            'last_wake': 0, 'input_devices': [], 'input_device': '',
            'last_recognized': '', 'last_recognized_at': 0, 'engine': 'direct',
            'enrollment_count': 0, 'enrollment_active': False, 'wake_score': 0.0,
            'speaker_match': 'untrained', 'wake_source': ''
        }

    def _templates_path(self):
        from core.paths import state_file
        return state_file('wake_acoustic_profile.npz')

    def has_profile(self) -> bool:
        # Numpy zip extraction is expensive. Re-read only when the profile changes.
        path = self._templates_path()
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = None
        if stamp != self._profile_cache_stamp:
            self._profile_cache_ready = (stamp is not None and
                len(wake_fingerprint.load(path)) == wake_fingerprint.REPETITIONS)
            self._profile_cache_stamp = stamp
        return self._profile_cache_ready

    def begin_enrollment(self) -> tuple[bool, str]:
        if not self.thread or not self.thread.is_alive():
            return False, 'شغّل الاستماع في الخلفية الأول'
        try:
            wake_fingerprint._numpy()
        except ImportError:
            return False, 'مكتبة numpy غير موجودة داخل نسخة برق'
        if self.live_active():
            return False, 'اقفل مكالمة برق الأول قبل تسجيل النداء'
        with self.lock:
            self._owner_samples=[]
            self._enrolling = []
            self._enrollment_active = True
            self._details.update(enrollment_active=True,enrollment_count=0,
                                 detail='قول يا برق 3 مرات، واسكت لحظة بين كل مرة')
        return True, 'قول يا برق ثلاث مرات'

    def cancel_enrollment(self) -> None:
        with self.lock:
            self._owner_samples=[]
            self._enrolling = []
            self._enrollment_active = False
            self._details.update(enrollment_active=False,enrollment_count=0)

    def delete_profile(self) -> None:
        self.cancel_enrollment()
        self._templates_path().unlink(missing_ok=True)
        from voice.owner_voice import delete
        delete()
        self._profile_cache_stamp = None
        self._profile_cache_ready = False

    def _enroll_sample(self, pcm: bytes) -> None:
        try:
            fingerprint = wake_fingerprint.signature(pcm)
            from voice import owner_voice
            owner_vector=owner_voice.embed(pcm) if owner_voice.available() else None
        except (ValueError, ImportError, RuntimeError):
            self._set(detail='العينة قصيرة أو صوتها مش واضح؛ قول يا برق بوضوح')
            return
        with self.lock:
            if not self._enrollment_active:return
            self._enrolling.append(fingerprint)
            if owner_vector is not None:self._owner_samples.append(owner_vector)
            count = len(self._enrolling)
            self._details.update(enrollment_count=count,
                                 detail=f'تم تسجيل {count} من 3 — قول يا برق مرة تانية' if count < 3 else 'جارٍ حفظ نداء برق')
            if count < wake_fingerprint.REPETITIONS:return
            templates = self._enrolling[:]
            owner_vectors=self._owner_samples[:]
            self._enrollment_active = False
            self._owner_samples=[]
            self._enrolling = []
        try:
            # Reject mixed speakers / highly inconsistent enrollment examples;
            # otherwise a noisy sample weakens owner-specific wake detection.
            scores = [wake_fingerprint.similarity(templates[i],templates[j])
                      for i in range(3) for j in range(i+1,3)]
            if min(scores) < .57:
                self._set(enrollment_active=False,detail='عينات النداء مختلفة جدًا؛ سجل 3 مرات بصوت واحد وبعيدًا عن الضوضاء')
                return
            if len(owner_vectors)==3:owner_voice.save(owner_vectors)
            wake_fingerprint.save(self._templates_path(), templates)
            self._set(enrollment_active=False,speaker_match='owner_enrolled' if len(owner_vectors)==3 else 'enrolled',
                      detail='اتحفظ نموذج صوتك ونداءك محليًا' if len(owner_vectors)==3 else 'اتحفظت بصمة النداء فقط؛ نموذج تمييز المتحدث غير جاهز')
        except (OSError, ValueError):
            self._set(enrollment_active=False,detail='فشل حفظ نداء برق؛ جرّب تاني')

    def start(self) -> tuple[bool, str]:
        if sys.platform != 'win32':
            return False, 'Direct Windows microphone capture requires Windows'
        if not model_path():
            return False, 'نموذج Vosk العربي مش موجود في ملفات برق؛ اختار تثبيته من Setup'
        if not native_dependencies_present():
            return False, 'مكتبات vosk و sounddevice مش موجودة داخل BARQ.exe'
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return True, 'running'
            self.stop_event = threading.Event()
            self._details.update(state='starting', detail='برق بيجهز الميكروفون الداخلي')
            self.thread = threading.Thread(target=self._run, name='BARQ-Direct-Microphone', daemon=True)
            self.thread.start()
        return True, 'starting'

    def stop(self) -> bool:
        with self.lock:
            thread = self.thread
            self.stop_event.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=4)
        with self.lock:
            if thread and thread.is_alive():
                self._details.update(state='stopping', detail='جارٍ تحرير الميكروفون')
                return False
            self.thread = None
            self._details.update(state='stopped', detail='')
            return True

    def status(self) -> dict:
        with self.lock:
            result = dict(self._details)
            result['running'] = bool(self.thread and self.thread.is_alive())
        if time.monotonic() - result['last_recognized_at'] > 12:
            result['last_recognized'] = ''
        result['profile_ready'] = self.has_profile()
        from voice import owner_voice
        result['owner_model_ready']=owner_voice.available()
        result['owner_voice_enrolled']=owner_voice.enrolled()
        # Last recognized text is short-lived in RAM only; no recording stored.
        return result

    def _set(self, **kwargs):
        with self.lock:
            self._details.update(kwargs)

    def _on_text(self, text: str) -> bool:
        text = str(text).strip()[:80]
        if text:
            self._set(last_recognized=text, last_recognized_at=time.monotonic())
        words = re.sub(r'[\u064b-\u065f\u0670\u0640]', '', text).lower().split()
        candidates = {'برق', 'برء', 'برأ', 'برك', 'بارق', 'براق'}
        return bool(words and (words[0] in candidates or (len(words) >= 2 and words[0] == 'يا' and words[1] in candidates)))

    def _run(self):
        try:
            import audioop  # Python 3.11 desktop runtime; imported only in worker
            import sounddevice as sd
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            self._set(state='loading', detail='تحميل نموذج اللغة العربية')
            model = Model(str(model_path()))
            try:
                devices = [dict(id=i, name=str(d['name'])[:85]) for i, d in enumerate(sd.query_devices())
                           if int(d.get('max_input_channels', 0)) > 0]
            except Exception:
                devices = []
            self._set(input_devices=devices[:80])
            cooldown = 0.0
            while not self.stop_event.is_set():
                if self.live_active() or time.monotonic() < cooldown:
                    self._set(state='waiting', level=0, detail='الميكروفون متاح لمكالمة برق المباشرة')
                    self.stop_event.wait(.35)
                    continue
                device_idx = self.device_preference()
                dev = sd.query_devices(device=device_idx, kind='input')
                native_rate = int(dev.get('default_samplerate') or 16000)
                if native_rate < 8000 or native_rate > 192000:
                    native_rate = 16000
                data_queue: queue.Queue[bytes] = queue.Queue(maxsize=8)
                last_callback_at = time.monotonic()
                def callback(indata, frames, timing, status):
                    nonlocal last_callback_at
                    if not self.stop_event.is_set():
                        last_callback_at = time.monotonic()
                        try:
                            data_queue.put_nowait(bytes(indata))
                        except queue.Full:
                            # Drop stale mic frames, not the newest audio, if Vosk
                            # runs behind real time on an ordinary Windows laptop.
                            try:
                                data_queue.get_nowait()
                                data_queue.put_nowait(bytes(indata))
                            except queue.Empty:
                                pass
                import vosk
                recognizer = create_recognizer(model, vosk)
                audio_resample = None
                partial_hits = 0
                wake_word_seen=False
                last_level_at = 0.0
                detected = False
                speech = bytearray()
                last_speech_at = 0.0
                input_stalled = False
                pre_roll = []
                templates = wake_fingerprint.load(self._templates_path())
                from voice import owner_voice
                if owner_voice.enrolled() and len(templates)!=wake_fingerprint.REPETITIONS:
                    self._set(state='error',detail='ملف نداء المتحدث غير مكتمل؛ أعد تسجيل بصمة النداء من الإعدادات')
                    return
                with sd.RawInputStream(device=device_idx, channels=1, dtype='int16', samplerate=native_rate,
                                       blocksize=max(512, native_rate // 10), callback=callback):
                    self._set(state='listening', detail=('الاستماع ببصمة النداء المسجلة' if templates else 'برق سامع الميكروفون مباشرة'),
                              input_device=str(dev.get('name', ''))[:85], level=0,
                              audio_seen=False, heard_speech=False)
                    while not self.stop_event.is_set():
                        if self.live_active():
                            break  # release device before Gemini Live takes it
                        try:
                            pcm = data_queue.get(timeout=.3)
                        except queue.Empty:
                            if time.monotonic() - last_callback_at >= INPUT_IDLE_RESTART_SECONDS:
                                input_stalled = True
                                self._set(state='reconnecting', level=0,
                                          detail='الميكروفون وقف إرسال صوت؛ برق بيعيد الاتصال تلقائيًا')
                                break  # close stream before trying another one
                            continue
                        now = time.monotonic()
                        if now - last_level_at > .25:
                            level = voice_level(pcm)
                            self._set(level=level, audio_seen=True, heard_speech=level >= 2,
                                      last_audio_at=time.time() if level >= 2 else 0)
                            last_level_at = now
                        if native_rate != 16000:
                            pcm, audio_resample = audioop.ratecv(pcm, 2, 1, native_rate, 16000, audio_resample)
                        # Enrollment / acoustic fallback are independent of the
                        # Arabic words guessed by Vosk; always resample first.
                        level_now = voice_level(pcm)
                        if not speech:
                            pre_roll.append(pcm)
                            pre_roll = pre_roll[-2:]
                        if level_now >= 2:
                            if not speech:
                                speech.extend(b''.join(pre_roll))
                            speech.extend(pcm)
                            last_speech_at = now
                        elif speech:
                            speech.extend(pcm)
                        elapsed = len(speech) / 32000.0
                        finished = bool(speech and ((now-last_speech_at >= .38) or elapsed >= 2.8))
                        # Temporarily skip Vosk during optional enrollment.
                        if self._enrollment_active:
                            if finished:
                                self._enroll_sample(bytes(speech))
                                templates=wake_fingerprint.load(self._templates_path())
                                speech.clear();pre_roll=[];last_speech_at=0.0
                            continue
                        if finished:
                            if len(templates) == wake_fingerprint.REPETITIONS:
                                try:
                                    matched, score = wake_fingerprint.matches(bytes(speech), templates)
                                    self._set(wake_score=round(score, 3))
                                    from voice import owner_voice
                                    if matched or (owner_voice.enrolled() and wake_word_seen):
                                        from voice import owner_voice
                                        if owner_voice.enrolled():
                                            owner_ok,owner_score=owner_voice.matches(bytes(speech))
                                            self._set(owner_score=owner_score)
                                            if not owner_ok:
                                                self._set(speaker_match='owner_not_matched')
                                                speech.clear();pre_roll=[];last_speech_at=0.0;wake_word_seen=False
                                                continue
                                        self._set(speaker_match='acoustic_match', wake_source='enrolled_phrase',
                                                  last_recognized='نداء صوتي مطابق', last_recognized_at=now)
                                        detected = True
                                        break
                                    else:
                                        self._set(speaker_match='not_matched')
                                except (ValueError, ImportError):
                                    self._set(speaker_match='unavailable')
                            speech.clear();pre_roll=[];last_speech_at=0.0;wake_word_seen=False
                        if recognizer.AcceptWaveform(pcm):
                            phrase = json.loads(recognizer.Result()).get('text', '')
                            partial_hits = 0
                            if phrase and self._on_text(phrase):wake_word_seen=True
                            if not templates and self._on_text(phrase):
                                self._set(wake_source='spoken_phrase',speaker_match='untrained')
                                detected = True
                                break
                        else:
                            partial = json.loads(recognizer.PartialResult()).get('partial', '')
                            if partial and self._on_text(partial):wake_word_seen=True
                            matched = (not templates and self._on_text(partial)) if partial else False
                            partial_hits = partial_hits + 1 if matched else 0
                            if partial_hits >= 3:
                                self._set(wake_source='spoken_phrase',speaker_match='untrained')
                                detected = True
                                break
                if detected and not self.stop_event.is_set():
                    self._set(state='activated', detail='برق سمع اسمه؛ بيفتح المحادثة',
                              last_wake=time.time(), level=0)
                    self.on_wake()
                    cooldown = time.monotonic() + 5
                elif input_stalled and not self.stop_event.is_set():
                    # Reset the device and recognizer together; leave stop()
                    # responsive even while recovering from disconnected input.
                    self.stop_event.wait(INPUT_RETRY_DELAY_SECONDS)
                else:
                    self._set(state='waiting', level=0)
        except Exception as exc:
            self._set(state='error', detail=f'فشل الميكروفون الداخلي: {type(exc).__name__}: {str(exc)[:115]}')
        finally:
            if self.stop_event.is_set():
                self._set(state='stopped', level=0)
