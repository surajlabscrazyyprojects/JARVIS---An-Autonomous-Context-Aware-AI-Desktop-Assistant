"""WAV encode/decode + analysis for the local TTS pipeline (no disk I/O)."""
from __future__ import annotations

import io
import wave

import numpy as np

_TARGET_SR = 24000


def encode_wav(audio: np.ndarray, sample_rate: int = _TARGET_SR) -> bytes:
    """Encode float32 audio ([-1,1]) to mono 16-bit PCM WAV bytes."""
    audio = np.asarray(audio, dtype=np.float32).ravel()
    if audio.size == 0:
        raise ValueError("cannot encode empty audio")
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def read_wav(wav_bytes: bytes) -> tuple[int, int, int, np.ndarray]:
    """Return (channels, sample_width, frame_rate, float32 array)."""
    if not wav_bytes:
        raise ValueError("empty wav bytes")
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        fr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype=np.float32)
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if ch > 1:
        arr = arr.reshape(-1, ch)
    return ch, sw, fr, arr


def write_wav(ch: int, sw: int, fr: int, arr: np.ndarray) -> bytes:
    return encode_wav(np.asarray(arr, dtype=np.float32), fr)


def concat_wav(wav_list: list[bytes]) -> bytes:
    chunks: list[np.ndarray] = []
    fr = _TARGET_SR
    for wb in wav_list:
        _c, _s, fr_i, arr = read_wav(wb)
        chunks.append(arr.ravel())
        fr = fr_i or fr
    if not chunks:
        raise ValueError("no wav chunks to concatenate")
    return encode_wav(np.concatenate(chunks), fr)


def rms(wav_bytes: bytes) -> float:
    """Root-mean-square amplitude in [0,1] for character sync (§27)."""
    try:
        _c, _s, _f, arr = read_wav(wav_bytes)
        arr = arr.ravel()
        return float(np.sqrt(np.mean(np.square(arr))) if arr.size else 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def wav_to_pcm(wav_bytes: bytes) -> tuple[int, int, bytes]:
    """Convert WAV -> (frame_rate, 1, int16 mono PCM bytes) for sink playback."""
    _c, _s, fr, arr = read_wav(wav_bytes)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    arr = np.clip(arr.ravel(), -1.0, 1.0)
    pcm = (arr * 32767.0).astype(np.int16).tobytes()
    return fr, 1, pcm