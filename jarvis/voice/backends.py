"""
Real voice backends for J.A.R.V.I.S. on Windows:

  * PyAudioMicSource  - owns the microphone via PyAudio (one stable stream).
  * WhisperSTT        - OFFLINE speech-to-text via faster-whisper (no network dependency,
                        so Google/network outages can no longer stop listening).
* GatewayTTS / NullTTS - text-to-speech. GatewayTTS talks to the local
  J.A.R.V.I.S. TTS gateway started by start_voice.py; NullTTS is a safe
  fallback / test backend.

If faster-whisper cannot download its model (offline machine), WhisperSTT raises STTError
and the listener's recovery loop retries; the operator is told clearly via health_check().
"""
from __future__ import annotations

import io
import logging
import time
import wave
from typing import Any, Optional

import numpy as np

try:  # pyaudio is optional on machines without an audio device (tests use sim backends)
    import pyaudio
except Exception:  # noqa: BLE001
    pyaudio = None

try:
    import soundfile as sf
except Exception:  # noqa: BLE001
    sf = None

logger = logging.getLogger("jarvis.voice.backends")


# --------------------------------------------------------------------------
# Microphone
# --------------------------------------------------------------------------
class PyAudioMicSource:
    # Keywords that indicate a loopback/system-audio device, NOT a real microphone.
    # These must be ignored — they capture computer output, not your voice.
    LOOPBACK_KEYWORDS = ("stereo mix", "what u hear", "wave out", "loopback", "virtual", "vb-audio", "voicemeeter")

    @staticmethod
    def list_microphones():
        """List available input devices (microphones only, no loopback). Returns [(index, name, is_loopback)]."""
        if pyaudio is None:
            return []
        pa = pyaudio.PyAudio()
        mics = []
        try:
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) < 1:
                    continue
                name = str(info.get("name", "")).lower()
                is_loopback = any(k in name for k in PyAudioMicSource.LOOPBACK_KEYWORDS)
                mics.append((i, info.get("name", ""), is_loopback))
        finally:
            try:
                pa.terminate()
            except Exception:
                pass
        return mics

    @staticmethod
    def _is_loopback_device(name: str) -> bool:
        n = (name or "").lower()
        return any(k in n for k in PyAudioMicSource.LOOPBACK_KEYWORDS)

    def _auto_select_mic(self) -> Optional[int]:
        """Pick the default microphone, explicitly skipping loopback devices."""
        if pyaudio is None or self._pa is None:
            return None
        try:
            default_idx = self._pa.get_default_input_device_info().get("index")
        except Exception:
            default_idx = None
        # Check if default is actually a loopback — if so, find a real mic
        if default_idx is not None:
            try:
                info = self._pa.get_device_info_by_index(int(default_idx))
                if not self._is_loopback_device(str(info.get("name", ""))):
                    return int(default_idx)
            except Exception:
                pass
        # Scan for first non-loopback input device
        for i in range(self._pa.get_device_count()):
            try:
                info = self._pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) < 1:
                    continue
                if not self._is_loopback_device(str(info.get("name", ""))):
                    return int(i)
            except Exception:
                continue
        return default_idx

    def __init__(self, sample_rate: int = 16000, device_index: Optional[int] = None,
                 frames_per_buffer: int = 320) -> None:
        self.sample_rate = sample_rate
        self.device_index = device_index  # None = auto-select real mic (never loopback)
        self.frames_per_buffer = frames_per_buffer
        self._pa = None
        self._stream = None
        self._opened = False
        self.healthy = False

    def open(self) -> None:
        if pyaudio is None:
            raise RuntimeError("pyaudio not available")
        if self._stream is not None and not self._stream.is_stopped():
            return
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        # Auto-select a REAL microphone if no explicit device given — never Stereo Mix / Loopback
        idx = self.device_index
        if idx is None:
            idx = self._auto_select_mic()
            if idx is not None:
                logger.info(f"[mic] auto-selected input device {idx}: {self._pa.get_device_info_by_index(idx).get('name')}")
            else:
                logger.warning("[mic] could not auto-select mic, using system default")
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            input_device_index=idx,
            frames_per_buffer=self.frames_per_buffer,
            stream_callback=None,
        )
        self._stream.start_stream()
        self._opened = True
        self.healthy = True

    def read(self, n: int, timeout: float = 0.3):
        if self._stream is None or not self._stream.is_active():
            raise RuntimeError("mic stream not active")
        try:
            raw = self._stream.read(n, exception_on_overflow=False)
        except Exception as exc:  # noqa: BLE001
            self.healthy = False
            raise RuntimeError(f"mic read failed: {exc}") from exc
        if raw is None or len(raw) == 0:
            return None
        ints = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return ints

    def close(self) -> None:
        self.healthy = False
        try:
            if self._stream is not None:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:  # noqa: BLE001
            pass
        self._stream = None
        try:
            if self._pa is not None:
                self._pa.terminate()
        except Exception:  # noqa: BLE001
            pass
        self._pa = None
        self._opened = False

    def reload(self) -> None:
        self.close()
        time.sleep(0.2)
        self.open()


# --------------------------------------------------------------------------
# Offline STT (faster-whisper)
# --------------------------------------------------------------------------
class WhisperSTT:
    def __init__(self, model_size: str = "base", device: str = "cpu",
                 compute_type: str = "int8") -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._load_lock = __import__("threading").Lock()

    def _ensure(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("faster_whisper not installed") from exc
        with self._load_lock:
            if self._model is None:
                self._model = WhisperModel(self.model_size, device=self.device,
                                           compute_type=self.compute_type)

    def reload(self) -> None:
        self._model = None
        self._ensure()

    def transcribe(self, audio: np.ndarray) -> str:
        self._ensure()
        a = np.asarray(audio, dtype=np.float32).ravel()
        if a.size == 0:
            return ""
        segments, _ = self._model.transcribe(a, language="en", beam_size=5,
                                             vad_filter=True, condition_on_previous_text=False)
        text = " ".join(s.text for s in segments).strip()
        return text


# --------------------------------------------------------------------------
# TTS
# --------------------------------------------------------------------------
class NullTTS:
    """Safe offline TTS that always succeeds (returns a short 16k blip)."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    def synthesize(self, text: str):
        sr = self.sample_rate
        t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
        blip = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        return blip

    def reload(self) -> None:
        pass


class GatewayTTS:
    """Talks to the local J.A.R.V.I.S. TTS gateway (start_voice.py)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8766,
                 voice: str = "jarvis", sample_rate: int = 24000) -> None:
        self.url = f"http://{host}:{port}/tts"
        self.voice = voice
        self.sample_rate = sample_rate
        self._session = None

    def synthesize(self, text: str):
        import urllib.request
        import json
        import urllib.error
        payload = json.dumps({"text": text, "voice": self.voice}).encode("utf-8")
        req = urllib.request.Request(self.url, data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.URLError as exc:
            raise RuntimeError(f"voice gateway unreachable: {exc}") from exc
        if sf is None:
            raise RuntimeError("soundfile unavailable to decode gateway audio")
        with io.BytesIO(raw) as buf:
            audio, sr = sf.read(buf)
        audio = np.asarray(audio, dtype=np.float32).ravel()
        return _Audio(audio, sr)

    def reload(self) -> None:
        pass


def pyaudio_play_fn(audio, sr: int, interrupted, device_index: Optional[int] = None) -> None:
    """Real speaker output. Checks `interrupted` so barge-in can stop playback early."""
    if pyaudio is None:
        time.sleep(min(30.0, float(np.asarray(audio).size) / max(1, sr)))
        return
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(format=pyaudio.paFloat32, channels=1, rate=int(sr),
                         output=True, output_device_index=device_index)
        stream.start_stream()
        data = np.asarray(audio, dtype=np.float32).ravel().tobytes()
        chunk = 2048
        for i in range(0, len(data), chunk):
            if interrupted.is_set():
                break
            stream.write(data[i:i + chunk], exception_on_overflow=False)
        stream.stop_stream()
        stream.close()
    finally:
        pa.terminate()


class _Audio:
    """Audio carrying its native sample rate."""

    def __init__(self, data: np.ndarray, sample_rate: int) -> None:
        self.data = data
        self.sample_rate = sample_rate

    def __array__(self, dtype=None):
        return self.data.astype(dtype) if dtype else self.data

    @property
    def size(self):
        return self.data.size
