from __future__ import annotations

import io
import wave
import numpy as np


def tensor_to_wav_bytes(audio_array: Any, sr: int = 24000) -> bytes:
    if hasattr(audio_array, "cpu"):
        audio_array = audio_array.cpu().numpy()
    arr = np.asarray(audio_array, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.squeeze()
    if arr.size == 0:
        arr = np.zeros(sr // 2, dtype=np.float32)

    # Peak-normalize
    max_val = np.max(np.abs(arr))
    if max_val > 1e-6:
        arr = arr / max_val * 0.95

    pcm = (arr * 32767.0).clip(-32768, 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm.tobytes())
    return buf.getvalue()
