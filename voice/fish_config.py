"""Fail-closed Fish Audio configuration validation (§4 of the voice spec).

Rules enforced here, tested in tests/test_fish_config.py:
  * Default and only free model: ``s2.1-pro-free``.
  * Paid models (s2.1-pro, s2-pro, s1, anything unknown) are REJECTED unless
    ALLOW_PAID_FISH_MODELS=true, with an explicit log warning on the paid path.
  * Missing/malformed model -> clear configuration error, never a silent
    fallback (Fish falls back to paid s2.1-pro server-side when the model is
    omitted or unrecognized — we must never send such a request).
  * Numeric ranges validated (temperature/top_p 0..1, latencies, timeouts).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("jarvis.fish_config")

FREE_MODEL = "s2.1-pro-free"
PAID_MODELS = ("s2.1-pro", "s2-pro", "s1")
KNOWN_MODELS = (FREE_MODEL,) + PAID_MODELS

VALID_LATENCY = ("low", "normal", "balanced")
VALID_FORMAT = ("mp3", "pcm", "wav", "opus")

WS_URL = "wss://api.fish.audio/v1/tts/live"
REST_URL = "https://api.fish.audio/v1/tts"


class FishConfigError(Exception):
    """Raised for any invalid Fish configuration (fail-closed)."""


@dataclass
class FishConfig:
    api_key: str = ""
    reference_id: str = ""
    model: str = FREE_MODEL
    base_url: str = "https://api.fish.audio"
    ws_url: str = WS_URL
    latency: str = "balanced"
    out_format: str = "mp3"
    sample_rate: int = 24000
    chunk_length: int = 200
    min_chunk_length: int = 50
    temperature: float = 0.70
    top_p: float = 0.70
    repetition_penalty: float = 1.20
    normalize: bool = True
    condition_on_previous_chunks: bool = True
    tts_timeout_ms: int = 15000
    connect_timeout_ms: int = 5000
    max_retries: int = 1
    allow_paid_models: bool = False
    # Usage guards (§14)
    max_requests_per_minute: int = 20
    max_utf8_bytes_per_session: int = 200_000
    max_response_chars: int = 2_000
    max_concurrent_streams: int = 1

    def validate(self) -> "FishConfig":
        """Validate everything; raise FishConfigError on any problem."""
        if not (self.api_key or "").strip():
            raise FishConfigError("FISH_API_KEY is missing — set it in .env (never commit it)")
        if not (self.reference_id or "").strip():
            raise FishConfigError("FISH_REFERENCE_ID is missing — configure a voice you are authorized to use")
        model = (self.model or "").strip()
        if not model:
            raise FishConfigError("FISH_MODEL is missing — default must be exactly 's2.1-pro-free'")
        if model not in KNOWN_MODELS:
            raise FishConfigError(
                f"FISH_MODEL {model!r} is unknown — refusing to send it "
                f"(Fish falls back to paid models for unrecognized values). "
                f"Use '{FREE_MODEL}'.")
        if model != FREE_MODEL and not self.allow_paid_models:
            raise FishConfigError(
                f"FISH_MODEL {model!r} is a paid model and ALLOW_PAID_FISH_MODELS is not 'true' — "
                f"blocked. Use '{FREE_MODEL}'.")
        if model != FREE_MODEL and self.allow_paid_models:
            log.warning("[Fish] PAID model %r explicitly enabled by configuration", model)
        if self.latency not in VALID_LATENCY:
            raise FishConfigError(f"FISH_LATENCY must be one of {VALID_LATENCY}, got {self.latency!r}")
        if self.out_format not in VALID_FORMAT:
            raise FishConfigError(f"FISH_FORMAT must be one of {VALID_FORMAT}, got {self.out_format!r}")
        for name, lo, hi in (("temperature", 0.0, 1.0), ("top_p", 0.0, 1.0)):
            v = float(getattr(self, name))
            if not (lo <= v <= hi):
                raise FishConfigError(f"FISH_{name.upper()} must be in [{lo},{hi}], got {v}")
        if not (0.5 <= float(self.repetition_penalty) <= 2.0):
            raise FishConfigError("FISH_REPETITION_PENALTY must be in [0.5, 2.0]")
        if not (100 <= int(self.chunk_length) <= 300):
            raise FishConfigError("FISH_CHUNK_LENGTH must be in [100, 300]")
        if not (0 <= int(self.min_chunk_length) <= 100):
            raise FishConfigError("FISH_MIN_CHUNK_LENGTH must be in [0, 100]")
        if int(self.tts_timeout_ms) <= 0 or int(self.connect_timeout_ms) <= 0:
            raise FishConfigError("Fish timeouts must be positive milliseconds")
        return self

    @property
    def is_free_mode(self) -> bool:
        return self.model == FREE_MODEL and not self.allow_paid_models

    @classmethod
    def from_env(cls, env: dict | None = None) -> "FishConfig":
        """Build from environment mapping (os.environ by default)."""
        e = env if env is not None else os.environ

        def _s(key: str, default: str = "") -> str:
            v = e.get(key)
            return v if v not in (None, "") else default

        def _i(key: str, default: int) -> int:
            try:
                return int(_s(key, str(default)))
            except ValueError:
                raise FishConfigError(f"{key} must be an integer, got {_s(key)!r}")

        def _f(key: str, default: float) -> float:
            try:
                return float(_s(key, str(default)))
            except ValueError:
                raise FishConfigError(f"{key} must be a number, got {_s(key)!r}")

        def _b(key: str, default: bool) -> bool:
            v = _s(key, "1" if default else "0")
            return v.strip().lower() in ("1", "true", "yes", "on")

        cfg = cls(
            api_key=_s("FISH_API_KEY") or _s("FISH_AUDIO_API_KEY"),
            reference_id=_s("FISH_REFERENCE_ID"),
            model=_s("FISH_MODEL", FREE_MODEL),
            base_url=_s("FISH_BASE_URL", "https://api.fish.audio"),
            ws_url=_s("FISH_TTS_WEBSOCKET_URL", WS_URL),
            latency=_s("FISH_LATENCY", "balanced"),
            out_format=_s("FISH_FORMAT", "mp3"),
            sample_rate=_i("FISH_SAMPLE_RATE", 24000),
            chunk_length=_i("FISH_CHUNK_LENGTH", 200),
            min_chunk_length=_i("FISH_MIN_CHUNK_LENGTH", 50),
            temperature=_f("FISH_TEMPERATURE", 0.70),
            top_p=_f("FISH_TOP_P", 0.70),
            repetition_penalty=_f("FISH_REPETITION_PENALTY", 1.20),
            normalize=_b("FISH_NORMALIZE", True),
            condition_on_previous_chunks=_b("FISH_CONDITION_ON_PREVIOUS_CHUNKS", True),
            tts_timeout_ms=_i("FISH_TTS_TIMEOUT_MS", 15000),
            connect_timeout_ms=_i("FISH_CONNECT_TIMEOUT_MS", 5000),
            max_retries=_i("FISH_MAX_RETRIES", 1),
            allow_paid_models=_b("ALLOW_PAID_FISH_MODELS", False),
            max_requests_per_minute=_i("FISH_MAX_REQUESTS_PER_MINUTE", 20),
            max_utf8_bytes_per_session=_i("FISH_MAX_UTF8_BYTES_PER_SESSION", 200_000),
            max_response_chars=_i("FISH_MAX_RESPONSE_LENGTH", 2_000),
            max_concurrent_streams=_i("FISH_MAX_CONCURRENT_STREAMS", 1),
        )
        return cfg.validate()
