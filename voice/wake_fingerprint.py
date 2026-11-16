"""Optional, user-enrolled acoustic wake phrase matcher.

Only a 36-frame *spectral template* is saved after an explicit enrollment.
Neither recorded PCM nor recognized words are stored. This is an activation
hint, not authentication, and never authorizes computer actions.
"""
from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile
import math

SAMPLE_RATE = 16000
REPETITIONS = 3


def _numpy():
    import numpy as np
    return np


def signature(pcm: bytes):
    """Fixed-size time/spectral fingerprint from single-channel 16-kHz PCM."""
    np = _numpy()
    samples = np.frombuffer(pcm[:len(pcm) & ~1], dtype='<i2').astype(np.float32) / 32768.0
    if samples.size < 4800 or samples.size > 16000 * 4:
        raise ValueError('Wake sample must last between 0.3 and 4 seconds')
    # Trim low-energy padding, but leave the attack/release of each word.
    chunks = samples[:(len(samples)//160)*160].reshape(-1,160)
    rms = np.sqrt(np.mean(chunks**2,axis=1))
    rms = np.convolve(rms, np.ones(3,dtype=np.float32)/3,mode='same')
    active = np.flatnonzero(rms > max(0.006, float(np.max(rms)) * .08))
    if active.size:
        left = max(0, int(active[0])*160 - 1600)
        right = min(len(samples), int(active[-1])*160 + 2400)
        samples = samples[left:right]
    if len(samples) < 3200:
        raise ValueError('No clear wake speech heard')
    # 25ms windows, 10ms hop. Mel filters + cepstral normalization remove
    # much of the device response/noise while retaining the phoneme pattern.
    nfft, window, hop = 512, 400, 160
    count = 1 + (len(samples) - window) // hop
    if count < 3:
        raise ValueError('Not enough speech')
    frames = np.stack([samples[i*hop:i*hop+window] for i in range(count)])
    frames *= np.hanning(window).astype(np.float32)
    power = abs(np.fft.rfft(frames, n=nfft, axis=1)) ** 2
    def hz_to_mel(freq): return 2595.0 * math.log10(1 + freq / 700.0)
    def mel_to_hz(mel): return 700.0 * (10 ** (mel / 2595.0) - 1)
    mels = np.linspace(hz_to_mel(110), hz_to_mel(7100), 28)
    bins = np.round(np.array([mel_to_hz(m) for m in mels]) * nfft / SAMPLE_RATE).astype(int)
    filt = np.zeros((26, nfft//2+1), np.float32)
    for i in range(26):
        low, mid, high = int(bins[i]), int(bins[i+1]), int(bins[i+2])
        if low < mid < high:
            filt[i,low:mid] = np.arange(mid-low)/(mid-low)
            filt[i,mid:high] = np.arange(high-mid)/(high-mid)
    logmel = np.log(np.maximum(power @ filt.T, 1e-9))
    dct = np.cos(np.pi / 26 * (np.arange(26)[None, :] + .5) * np.arange(1, 14)[:, None])
    features = (logmel @ dct.T).astype(np.float32)
    features -= features.mean(axis=0, keepdims=True)
    features /= np.maximum(features.std(axis=0, keepdims=True), .25)
    target = 36
    grid = np.linspace(0, len(features)-1, target)
    reduced = np.stack([np.interp(grid, np.arange(len(features)), features[:,j]) for j in range(13)],axis=1)
    return reduced.astype(np.float32)


def similarity(a, b) -> float:
    np = _numpy()
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    if a.shape != (36,13) or b.shape != (36,13):
        raise ValueError('Invalid wake template dimensions')
    # A small local time warp tolerates natural speaking speed changes.
    costs = np.linalg.norm(a[:,None,:]-b[None,:,:],axis=2) / math.sqrt(13)
    dp = np.full((37,37), np.inf, np.float32);dp[0,0] = 0
    for i in range(1,37):
        for j in range(max(1,i-6), min(36,i+6)+1):
            dp[i,j] = costs[i-1,j-1] + min(dp[i-1,j-1],dp[i,j-1],dp[i-1,j])
    return max(0.0, min(1.0, float(1.0/(1.0+dp[36,36]/36.0))))


def threshold(templates) -> float:
    """Never accept an unknown speaker merely because one template matches poorly."""
    if len(templates) < REPETITIONS:
        return 1.0
    scores = [similarity(templates[i],templates[j]) for i in range(len(templates)) for j in range(i+1,len(templates))]
    return max(.61, min(.83, sorted(scores)[len(scores)//2] - .09))


def matches(pcm:bytes, templates) -> tuple[bool,float]:
    if len(templates) < REPETITIONS:return False, 0.0
    candidate = signature(pcm)
    # One noisy template may accidentally match a second speaker. Demand
    # agreement from at least TWO of the three owner-enrolled wake examples.
    # This remains a wake-PHRASE resemblance check, not speaker biometrics.
    scores = sorted(similarity(candidate, t) for t in templates)
    consensus = scores[-2]
    return consensus >= threshold(templates), consensus


def load(path: Path):
    try:
        np = _numpy()
        with np.load(path, allow_pickle=False) as saved:
            values = saved['templates']
            if values.shape != (REPETITIONS,36,13) or not np.isfinite(values).all():
                return []
            return [x.copy() for x in values]
    except (ImportError, OSError, KeyError, ValueError, BadZipFile, EOFError):
        return []


def save(path: Path, templates) -> None:
    np = _numpy()
    values = np.asarray(templates,dtype=np.float32)
    if values.shape != (REPETITIONS,36,13) or not np.isfinite(values).all():
        raise ValueError('Incomplete wake enrollment')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('wb') as file:
        np.savez_compressed(file, templates=values)
    temp.replace(path)
