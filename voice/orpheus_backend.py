"""OrpheusBackend - the ACTIVE provider contract ("orpheus" provider, spec §1/§5).

This is the front/interface backend: config reports provider="orpheus". If the
`orpheus-tts` runtime is actually installed AND usable it is used. On this
CPU-only target it is not installed, so this backend reports unavailable and
the service truthfully reports VOICE_DEGRADED; the configured kokoro engine
then provides synthesis (explicitly configured, never a silent switch).

APIs are used only if present (inspect-at-runtime); we never invent controls.
"""
from __future__ import annotations

from typing import Iterator, Optional

from .log import logger
from .tts_backend import TTSBackend, TTSError, TTSUnavailable


class OrpheusBackend(TTSBackend):
    name = "orpheus"

    def __init__(self, cfg):
        self.cfg = cfg
        self._model = None
        self._warmed = False
        self._err = ""

    def _importable(self) -> bool:
        try:
            import orpheus  # noqa: F401
            return True
        except Exception as e:  # noqa: BLE001
            self._err = f"orpheus-tts not installed ({e})"
            return False

    def _ensure(self):
        if self._model is not None:
            return
        if not self._importable():
            raise TTSUnavailable(self._err or "orpheus-tts not installed")
        try:
            from orpheus import OrpheusModel
            model_id = self.cfg.model if "Orpheus" in self.cfg.model else "canopyai/Orpheus-3B-0.1-ft"
            self._model = OrpheusModel(model_name=model_id)
            logger.info(f"[TTS] orpheus model loaded: {model_id}")
        except Exception as e:  # noqa: BLE001
            self._err = f"orpheus load failed: {e}"
            self._model = None
            raise TTSUnavailable(self._err) from e

    def health_check(self) -> tuple[bool, str]:
        if not self._importable():
            return False, self._err
        if self._warmed:
            return True, "ready (warm)"
        return True, "importable (not yet warmed)"

    def warmup(self) -> tuple[bool, str]:
        try:
            wav = self.synthesize("Voice system ready.")
            if len(wav) > 44:
                self._warmed = True
                return True, "ready (synthesis verified)"
            return False, "warmup produced no audio"
        except Exception as e:  # noqa: BLE001
            return False, f"warmup failed: {e}"

    def _gen_kwargs(self, voice: Optional[str], speed: float):
        # Real orpheus-tts kwargs: voice (persona string) and temperature/top_p.
        # Only pass what the installed signature accepts (inspect at runtime).
        import inspect
        kwargs: dict = {}
        try:
            gen = getattr(self._model, "generate_speech", None) or \
                getattr(self._model, "generate", None)
            params = inspect.signature(gen).parameters if gen else {}
            if "voice" in params:
                kwargs["voice"] = voice or "leo"
            if "temperature" in params:
                kwargs["temperature"] = self.cfg.temperature
            if "top_p" in params:
                kwargs["top_p"] = self.cfg.top_p
        except Exception:  # noqa: BLE001
            pass
        # Orpheus has no 'speed' control; ignore (identity preserved).
        return kwargs

    def synthesize(self, text: str, voice: Optional[str] = None,
                   speed: float = 1.0, pitch_cents: int = 0) -> bytes:
        self._ensure()
        try:
            kwargs = self._gen_kwargs(voice, speed)
            method = getattr(self._model, "generate_speech", None) or \
                getattr(self._model, "generate", None)
            if method is None:
                raise TTSUnavailable("no orpheus generate method exposed")
            audio = method(text, **kwargs)
            import numpy as np
            if hasattr(audio, "numpy"):
                audio = audio.numpy()
            from .wav import encode_wav
            return encode_wav(np.asarray(audio, dtype="float32").ravel())
        except TTSUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            raise TTSError(f"orpheus synthesis failed: {e}") from e

    def stream(self, text: str, voice: Optional[str] = None,
               speed: float = 1.0, pitch_cents: int = 0
               ) -> Iterator[tuple[float, bytes]]:
        self._ensure()
        import numpy as np
        from .wav import encode_wav, rms
        method = getattr(self._model, "generate_speech_stream", None)
        if method is None:
            wav = self.synthesize(text, voice=voice, speed=speed, pitch_cents=pitch_cents)
            yield rms(wav), wav
            return
        kwargs = self._gen_kwargs(voice, speed)
        for chunk in method(text, **kwargs):
            arr = np.asarray(chunk, dtype="float32").ravel()
            if not arr.size:
                continue
            wav = encode_wav(arr)
            yield rms(wav), wav

    def list_voices(self) -> list[str]:
        return ["tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe"]

    def stop(self) -> None:
        try:
            if self._model is not None and hasattr(self._model, "stop"):
                self._model.stop()
        except Exception:  # noqa: BLE001
            pass

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def shutdown(self) -> None:
        self._model = None
        self._warmed = False