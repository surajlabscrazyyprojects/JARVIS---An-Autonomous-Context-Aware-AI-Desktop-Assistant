"""Structured logging for the voice subsystem ([TTS] prefixed)."""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger("jarvis.tts")


def configure_logging(debug: bool = False, level: Optional[int] = None):
    lvl = level if level is not None else (logging.DEBUG if debug else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [TTS] %(levelname)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(lvl)
    return logger


class TTSMetrics:
    """Lightweight latency/duration recorder (no conversation content logged)."""

    def __init__(self):
        self.last_latency = 0.0
        self.last_duration = 0.0
        self.total_generated = 0
        self.errors = 0
        self.fallbacks = 0

    def record(self, latency: float, duration: float):
        self.last_latency = round(latency, 3)
        self.last_duration = round(duration, 3)
        self.total_generated += 1

    def record_error(self):
        self.errors += 1

    def record_fallback(self):
        self.fallbacks += 1

    def snapshot(self) -> dict:
        return {
            "last_latency_s": self.last_latency,
            "last_duration_s": self.last_duration,
            "total_generated": self.total_generated,
            "errors": self.errors,
            "fallbacks": self.fallbacks,
        }


def now() -> float:
    return time.time()
