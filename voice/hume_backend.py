"""Hume Octave text-to-speech backend.

Credentials stay server-side in HUME_API_KEY. The backend returns WAV bytes to
the existing gateway, so the HUD and microphone pipeline remain unchanged.
"""
from __future__ import annotations

import base64
import io
import threading
from typing import Iterator, Optional

import requests

from .config import VoiceConfig
from .fish_backend import FishBackend
from .log import logger
from .tts_backend import TTSBackend, TTSError, TTSUnavailable
from .wav import rms


class HumeBackend(TTSBackend):
    name = "hume"

    def __init__(self, cfg: VoiceConfig):
        self.cfg = cfg
        self._api_key = (getattr(cfg, "hume_api_key", "") or "").strip()
        if not self._api_key:
            raise TTSUnavailable("HUME_API_KEY is not configured")
        self._voice = getattr(cfg, "hume_voice_id", "") or cfg.voice
        self._voice_provider = getattr(cfg, "hume_voice_provider", "HUME_AI")
        self._url = getattr(cfg, "hume_url", "https://api.hume.ai/v0/tts")
        self._session = requests.Session()
        self._lock = threading.Lock()

    def health_check(self) -> tuple[bool, str]:
        return (bool(self._api_key), "configured" if self._api_key else "HUME_API_KEY missing")

    def warmup(self) -> tuple[bool, str]:
        try:
            audio = self.synthesize("Voice system ready.", voice=self._voice)
            return (len(audio) > 44, "ready (Hume synthesis verified)")
        except Exception as exc:  # noqa: BLE001
            return False, f"Hume warmup failed: {exc}"

    def _request(self, text: str, voice: Optional[str], speed: float) -> bytes:
        payload = {
            "utterances": [{
                "text": text,
                "voice": {"id": voice or self._voice, "provider": self._voice_provider},
                "speed": max(0.7, min(1.4, float(speed))),
            }],
            "format": {"type": "wav"},
            "version": "2",
            "num_generations": 1,
            "split_utterances": False,
        }
        with self._lock:
            resp = self._session.post(self._url, headers={
                "X-Hume-Api-Key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }, json=payload, timeout=30)
        if not resp.ok:
            raise TTSError(f"Hume HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
            audio = data["generations"][0]["audio"]
            raw = base64.b64decode(audio)
        except Exception as exc:  # noqa: BLE001
            raise TTSError(f"invalid Hume response: {exc}") from exc
        if raw[:4] == b"RIFF":
            return raw
        # Hume may return encoded audio despite the WAV request. Reuse the
        # existing proven decoder path without changing the active playback API.
        try:
            return FishBackend._mp3_to_wav_bytes(self, raw)
        except Exception as exc:  # noqa: BLE001
            raise TTSError(f"Hume audio decode failed: {exc}") from exc

    def synthesize(self, text: str, voice: Optional[str] = None,
                   speed: float = 1.0, pitch_cents: int = 0) -> bytes:
        return self._request(text, voice, speed)

    def stream(self, text: str, voice: Optional[str] = None,
               speed: float = 1.0, pitch_cents: int = 0) -> Iterator[tuple[float, bytes]]:
        wav = self.synthesize(text, voice=voice, speed=speed, pitch_cents=pitch_cents)
        yield rms(wav), wav

    def list_voices(self) -> list[str]:
        return [self._voice] if self._voice else []

    def stop(self) -> None: pass
    def pause(self) -> None: pass
    def resume(self) -> None: pass
    def shutdown(self) -> None:
        self._session.close()
