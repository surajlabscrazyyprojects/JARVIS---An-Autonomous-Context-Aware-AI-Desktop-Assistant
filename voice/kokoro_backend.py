"""KokoroBackend - the ACTUAL synthesis engine (CPU-fast, installed, offline).

Facts verified against the installed implementation (kokoro==0.9.4):
  KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', device='cpu')
  pipeline(text, voice='am_michael', speed=float, split_pattern=r'(?<=[.!?])\\s+')
    -> generator of (graphemes, phonemes, audio float32 @ 24000 Hz)

Only controls Kokoro actually supports are used (voice + speed). Emotional
delivery is layered on the SAME speaker identity with a real pitch shift
(NEUTRAL vs EXCITED/EMPATHETIC delivery differs, identity never changes).
The model is loaded ONCE into the long-running gateway process.
"""
from __future__ import annotations

import gc
import os
import threading
from collections import OrderedDict
from typing import Iterator, Optional

import numpy as np

from .log import logger
from .tts_backend import TTSBackend, TTSError, TTSUnavailable
from .wav import encode_wav, rms

_SR = 24000
_SPLIT = r"(?<=[.!?])\s+"


class KokoroBackend(TTSBackend):
    name = "kokoro"

    def __init__(self, cfg):
        self.cfg = cfg
        self._pipe = None
        self._lock = threading.Lock()
        self._warmed = False
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._cache: "OrderedDict[str, bytes]" = OrderedDict()

    # -- availability / load -------------------------------------------
    def _importable(self) -> bool:
        try:
            import kokoro  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def _ensure(self):
        if self._pipe is not None:
            return
        with self._lock:
            if self._pipe is not None:
                return
            if not self._importable():
                raise TTSUnavailable("kokoro is not installed")
            # Force offline: only weights already in the local HF cache.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            try:
                from kokoro import KPipeline
                self._pipe = KPipeline(lang_code=self.cfg.lang_code,
                                       repo_id=self.cfg.model,
                                       device=self.cfg.device)
                logger.info(f"[TTS] kokoro model loaded: {self.cfg.model}")
            except Exception as e:  # noqa: BLE001
                self._pipe = None
                raise TTSUnavailable(f"kokoro model load failed: {e}") from e

    def health_check(self) -> tuple[bool, str]:
        if not self._importable():
            return False, "kokoro not installed"
        if self._warmed:
            return True, "ready (warm)"
        return True, "importable (not yet warmed)"

    def warmup(self) -> tuple[bool, str]:
        try:
            self._ensure()
            wav = self._synthesize("Voice system ready.", cache=False)
            if len(wav) > 44:
                self._warmed = True
                return True, "ready (synthesis verified)"
            return False, "warmup produced no audio"
        except Exception as e:  # noqa: BLE001
            return False, f"warmup failed: {e}"

    # -- core -----------------------------------------------------------
    def _pitch_shift(self, y: np.ndarray, cents: int) -> np.ndarray:
        try:
            from librosa.effects import pitch_shift
        except Exception:  # noqa: BLE001
            return y  # pitch unavailable -> honest: only pace changes
        try:
            return np.asarray(
                pitch_shift(y.astype(np.float32), sr=_SR, n_steps=cents / 100.0),
                dtype=np.float32)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[TTS] pitch shift skipped: {e}")
            return y

    def _synthesize(self, text: str, voice: Optional[str] = None,
                    speed: float = 1.0, pitch_cents: int = 0,
                    cache: bool = True) -> bytes:
        if self._stop.is_set():
            raise TTSError("engine stopped")
        voice = voice or self.cfg.voice
        if voice not in self.list_voices():
            voice = "am_michael"
        key = f"{voice}:{speed:.3f}:{pitch_cents}:{len(text)}:{hash(text)}"
        if cache:
            with self._lock:
                hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        try:
            parts: list[np.ndarray] = []
            for _gs, _ps, audio in self._pipe(text, voice=voice, speed=float(speed),
                                              split_pattern=_SPLIT):
                arr = np.asarray(audio, dtype=np.float32).ravel()
                if arr.size:
                    parts.append(arr)
            if not parts:
                raise TTSError("empty synthesis")
            out = np.concatenate(parts)
            if pitch_cents:
                out = self._pitch_shift(out, int(pitch_cents))
            wav = encode_wav(out, _SR)
        except TTSUnavailable:
            raise
        except TTSError:
            raise
        except Exception as e:  # noqa: BLE001
            raise TTSError(f"kokoro synthesis failed: {e}") from e

        is_short = len(text.split()) <= 6
        if cache and is_short:
            with self._lock:
                self._cache[key] = wav
                while len(self._cache) > self.cfg.cache_max_entries:
                    self._cache.popitem(last=False)
        return wav

    def synthesize(self, text: str, voice: Optional[str] = None,
                   speed: float = 1.0, pitch_cents: int = 0) -> bytes:
        self._ensure()
        return self._synthesize(text, voice=voice, speed=speed,
                                pitch_cents=pitch_cents, cache=self.cfg.cache_enabled)

    def stream(self, text: str, voice: Optional[str] = None,
               speed: float = 1.0, pitch_cents: int = 0
               ) -> Iterator[tuple[float, bytes]]:
        self._ensure()
        voice = voice or self.cfg.voice
        if voice not in self.list_voices():
            voice = "am_michael"
        for _gs, _ps, audio in self._pipe(text, voice=voice, speed=float(speed),
                                          split_pattern=_SPLIT):
            if self._stop.is_set():
                break
            arr = np.asarray(audio, dtype=np.float32).ravel()
            if not arr.size:
                continue
            if pitch_cents:
                arr = self._pitch_shift(arr, int(pitch_cents))
            wav = encode_wav(arr, _SR)
            yield rms(wav), wav

    def list_voices(self) -> list[str]:
        base = ["am_michael", "am_puck", "am_adam", "am_eric", "am_liam",
                "am_onyx", "af_heart"]
        try:
            from huggingface_hub import snapshot_download  # noqa: F401
            from pathlib import Path
            cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
            hub = cache / "hub" / "models--hexgrad--Kokoro-82M" / "snapshots"
            if hub.exists():
                snap = next(hub.iterdir(), None)
                if snap:
                    voices = sorted(p.stem for p in (snap / "voices").glob("*.pt"))
                    if voices:
                        return voices
        except Exception:  # noqa: BLE001
            pass
        return base

    def stop(self) -> None:
        self._stop.set()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            self._pipe = None
            self._cache.clear()
        self._warmed = False
        gc.collect()