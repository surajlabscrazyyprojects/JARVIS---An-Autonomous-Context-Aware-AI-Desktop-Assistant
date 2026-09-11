from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from jarvis.voice.exceptions import VoiceInitError

VALID_ENGINES = {
    "chatterbox-nano",
    "chatterbox-turbo",
    "fish-audio",
    "elevenlabs",
    "fake-engine",
    "system",
}


@dataclass
class VoiceEngineConfig:
    engine: str = "chatterbox-nano"
    temperature: float = 0.7
    http_port: int = 8766
    max_text_chars: int = 1000

    def reference_path(self) -> Path:
        root = Path(__file__).resolve().parent.parent.parent
        return root / "voice" / "references" / "jarvis_reference.wav"


def load_voice_config(settings: Dict[str, Any]) -> VoiceEngineConfig:
    cfg = VoiceEngineConfig()
    tts_dict = settings.get("tts", {})
    if "engine" in tts_dict:
        cfg.engine = str(tts_dict["engine"])
    if "temperature" in tts_dict:
        cfg.temperature = float(tts_dict["temperature"])

    if "VOICE_ENGINE" in os.environ:
        cfg.engine = os.environ["VOICE_ENGINE"]
    if "VOICE_HTTP_PORT" in os.environ:
        cfg.http_port = int(os.environ["VOICE_HTTP_PORT"])
    if "VOICE_MAX_TEXT_CHARS" in os.environ:
        cfg.max_text_chars = int(os.environ["VOICE_MAX_TEXT_CHARS"])

    if cfg.engine not in VALID_ENGINES:
        raise VoiceInitError(f"Unsupported voice engine: {cfg.engine}")

    return cfg
