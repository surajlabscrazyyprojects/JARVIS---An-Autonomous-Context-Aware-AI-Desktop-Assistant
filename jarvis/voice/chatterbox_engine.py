from __future__ import annotations

import io
import wave
import numpy as np
from typing import Any, Optional

from jarvis.voice.audio import tensor_to_wav_bytes
from jarvis.voice.config import VoiceEngineConfig
from jarvis.voice.engine import VoiceEngine


class ChatterboxNanoEngine(VoiceEngine):
    name: str = "chatterbox-nano"

    def __init__(self, config: Optional[VoiceEngineConfig] = None) -> None:
        self.config = config or VoiceEngineConfig()
        self._ready = False

    def initialize(self) -> None:
        self._ready = True

    def is_ready(self) -> bool:
        return self._ready

    def synthesize(self, text: str, **kwargs: Any) -> bytes:
        # Generate simulated clean speech audio sine/formant wave
        sr = 24000
        dur = max(0.5, len(text.split()) * 0.35)
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        wave_data = (0.3 * np.sin(2 * np.pi * 220 * t) + 0.15 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return tensor_to_wav_bytes(wave_data, sr)

    def shutdown(self) -> None:
        self._ready = False
