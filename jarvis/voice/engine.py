from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from jarvis.voice.config import VoiceEngineConfig
from jarvis.voice.exceptions import VoiceNotReadyError, VoiceSynthesisError


class VoiceEngine:
    name: str = "base-engine"

    def initialize(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True

    def synthesize(self, text: str, **kwargs: Any) -> bytes:
        raise NotImplementedError

    def shutdown(self) -> None:
        pass


@dataclass
class VoiceMetrics:
    synthesis_count: int = 0
    total_synthesis_seconds: float = 0.0
    total_audio_seconds: float = 0.0

    @property
    def average_synthesis_seconds(self) -> float:
        return self.total_synthesis_seconds / self.synthesis_count if self.synthesis_count > 0 else 0.0

    @property
    def rtf(self) -> float:
        return self.total_synthesis_seconds / self.total_audio_seconds if self.total_audio_seconds > 0 else 0.5


class VoiceEngineManager:
    def __init__(self, config: VoiceEngineConfig, engine: Optional[VoiceEngine] = None) -> None:
        self.config = config
        self.engine = engine or VoiceEngine()
        self._lock = threading.Lock()
        self.metrics = VoiceMetrics()

    def initialize(self) -> None:
        self.engine.initialize()

    def is_ready(self) -> bool:
        return self.engine.is_ready()

    def synthesize(self, text: str, **kwargs: Any) -> bytes:
        if not self.is_ready():
            raise VoiceNotReadyError("Voice engine is not initialized or ready.")

        with self._lock:
            t0 = time.perf_counter()
            try:
                wav_bytes = self.engine.synthesize(text, **kwargs)
                dur = time.perf_counter() - t0
                audio_dur = max(0.5, len(wav_bytes) / (24000 * 2))
                self.metrics.synthesis_count += 1
                self.metrics.total_synthesis_seconds += dur
                self.metrics.total_audio_seconds += audio_dur
                return wav_bytes
            except Exception as exc:
                if isinstance(exc, VoiceNotReadyError):
                    raise
                raise VoiceSynthesisError(f"Speech synthesis failed: {exc}") from exc

    def shutdown(self) -> None:
        self.engine.shutdown()
