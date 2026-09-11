"""
TTS backend contract shared by the local engine family.

One active provider (`provider` in config, default "orpheus") exposes the
service interface; the actual synthesis engine (`engine` in config, default
"kokoro") implements these primitives. Engines are loaded ONCE into a long
running process and never for every sentence.

Every backend reports its true health. If the active provider is unavailable
the service reports VOICE_DEGRADED truthfully instead of silently switching
between engines.
"""
from __future__ import annotations

import abc
from typing import Iterator, Optional


class TTSUnavailable(Exception):
    """The configured TTS engine cannot be reached/loaded right now."""


class TTSError(Exception):
    """TTS synthesis failed for a specific request."""


class TTSBackend(abc.ABC):
    name: str = "generic"

    def available(self) -> bool:
        """True if the engine is importable/usable on this machine (no load)."""
        try:
            ok, _ = self.health_check()
            return bool(ok)
        except Exception:  # noqa: BLE001
            return False

    @abc.abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Return (ok, detail). Never raises."""

    @abc.abstractmethod
    def warmup(self) -> tuple[bool, str]:
        """Load the model once and verify real synthesis (no fake 'ready')."""

    @abc.abstractmethod
    def synthesize(self, text: str, voice: Optional[str] = None,
                   speed: float = 1.0, pitch_cents: int = 0) -> bytes:
        """Return mono 16-bit PCM WAV bytes. Raises TTSUnavailable/TTSError."""

    @abc.abstractmethod
    def stream(self, text: str, voice: Optional[str] = None,
               speed: float = 1.0, pitch_cents: int = 0
               ) -> Iterator[tuple[float, bytes]]:
        """Yield (segment_rms, wav_bytes) per speech chunk as generated.
        Text chunk N is played while chunk N+1 is synthesized."""

    @abc.abstractmethod
    def list_voices(self) -> list[str]:
        """Available voice ids for the engine."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Cancel any in-flight generation."""

    @abc.abstractmethod
    def pause(self) -> None:
        """Hold in-flight generation (backpressure hint)."""

    @abc.abstractmethod
    def resume(self) -> None:
        """Resume generation."""

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Release the model and worker resources."""