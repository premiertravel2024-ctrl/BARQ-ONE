"""Local neural speaker resemblance for a user-enrolled wake; never an authority grant."""
from __future__ import annotations
import hashlib,importlib.util,threading
from core.paths import resource,state_file
MODEL='wespeaker_en_voxceleb_resnet34_LM.onnx'
SHA256='e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012'
_guard=threading.RLock();_extractor=None

def available():
 return resource('models','speaker',MODEL).is_file() and importlib.util.find_spec('sherpa_onnx') is not None

def enrolled():return state_file('owner_voice.npz').is_file()

def embed(pcm:bytes):
 import numpy as np
 global _extractor
 samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
 if not 4800<=samples.size<=64000 or not np.isfinite(samples).all() or np.sqrt(np.mean(samples*samples))<.004:raise ValueError('عينة الصوت قصيرة أو ضعيفة')
 with _guard:
  if _extractor is None:
   import sherpa_onnx
   path=resource('models','speaker',MODEL)
   if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:raise ValueError('نموذج تمييز الصوت لم يجتز التحقق')
   config=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(path),num_threads=1,debug=False,provider='cpu')
   if not config.validate():raise ValueError('إعداد نموذج الصوت غير صالح')
   _extractor=sherpa_onnx.SpeakerEmbeddingExtractor(config)
  stream=_extractor.create_stream();stream.accept_waveform(sample_rate=16000,waveform=samples);stream.input_finished()
  if not _extractor.is_ready(stream):raise ValueError('قول يا برق بوضوح أطول قليلًا')
  vector=np.asarray(_extractor.compute(stream),dtype=np.float32)
  if vector.ndim!=1 or not 64<=vector.size<=1024 or not np.isfinite(vector).all() or np.linalg.norm(vector)<1e-6:raise ValueError('بصمة الصوت غير صالحة')
  return vector/np.linalg.norm(vector)

def save(vectors):
 import numpy as np
 values=np.asarray(vectors,dtype=np.float32)
 if values.ndim!=2 or values.shape[0]!=3 or not np.isfinite(values).all():raise ValueError('مطلوب 3 عينات صوت متسقة')
 values=values/np.maximum(np.linalg.norm(values,axis=1,keepdims=True),1e-8)
 if min(float(values[i]@values[j]) for i in range(3) for j in range(i+1,3))<.65:raise ValueError('عينات المتحدث مختلفة؛ أعد التسجيل في مكان أهدى')
 path=state_file('owner_voice.npz');tmp=path.with_suffix('.tmp')
 with _guard:
  with tmp.open('wb') as f:np.savez_compressed(f,embeddings=values)
  tmp.replace(path)

def matches(pcm,*,embedding=None):
 import numpy as np
 try:
  path=state_file('owner_voice.npz')
  if not path.is_file() or path.stat().st_size>100000:return False,0.0
  with np.load(path,allow_pickle=False) as data:values=data['embeddings']
  if values.ndim!=2 or values.shape[0]!=3 or not np.isfinite(values).all():return False,0.0
  vector=embedding if embedding is not None else embed(pcm)
  if values.shape[1]!=len(vector):return False,0.0
  scores=values@vector
  score=float(np.sort(scores)[-2])
  return bool(np.count_nonzero(scores>=.65)>=2),round(score,3)
 except (ValueError,OSError,ImportError,RuntimeError):return False,0.0

def delete():state_file('owner_voice.npz').unlink(missing_ok=True)
