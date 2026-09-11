"""
VoiceEngine - orchestrates the ONE active local TTS pipeline:

  reply text
    -> SpeechPlanner (preprocess + sentence chunks + emotion)
    -> engine backend (kokoro now; orpheus interface when its runtime exists)
    -> WAV bytes (per chunk, streamed while the previous chunk plays)

Voice identity is one male young-adult American accent across emotions;
emotion changes PERFORMANCE, never the speaker.
"""
from __future__ import annotations

import inspect
import time
from typing import Iterator, Optional

from .character_registry import get_reference_id, normalize_character, get_display_name
from .config import VoiceConfig
from .emotion import CharacterProfile, EmotionDirector, EmotionState, SpeechPerformance
from .log import configure_logging, logger
from .speech_planner import SpeechPlanner
from .tts_backend import TTSBackend, TTSError, TTSUnavailable
from .wav import concat_wav

# Voice health states (spec §32).
VOICE_OFFLINE = "VOICE_OFFLINE"
VOICE_STARTING = "VOICE_STARTING"
VOICE_LOADING = "VOICE_LOADING"
VOICE_READY = "VOICE_READY"
VOICE_DEGRADED = "VOICE_DEGRADED"
VOICE_FAILED = "VOICE_FAILED"


def build_engine_backend(cfg: VoiceConfig) -> TTSBackend:
    """Build the configured synthesis engine. Raises TTSUnavailable if the
    explicitly configured engine cannot even be constructed. No silent
    multi-engine fallback: if the configured engine is unusable, the caller
    reports a truthful degraded state."""
    engine = (cfg.engine or "fish").lower()
    if engine == "fish":
        from .fish_backend import FishBackend
        return FishBackend(cfg)
    if engine == "hume":
        from .hume_backend import HumeBackend
        return HumeBackend(cfg)
    if engine == "orpheus":
        from .orpheus_backend import OrpheusBackend
        b = OrpheusBackend(cfg)
        if not b.available():
            raise TTSUnavailable(b._err or "orpheus runtime not usable")
        return b
    if engine == "kokoro":
        from .kokoro_backend import KokoroBackend
        return KokoroBackend(cfg)
    raise TTSUnavailable(f"unknown tts engine: {engine}")


class VoiceEngine:
    def __init__(self, cfg: VoiceConfig, backend: Optional[TTSBackend] = None):
        configure_logging(cfg.debug)
        self.cfg = cfg
        # Hume voice identity is authoritative; persisted Fish character state
        # must never override the explicitly configured Hume voice.
        if (cfg.engine or '').lower() == 'hume':
            cfg.voice = getattr(cfg, 'hume_voice_id', None) or cfg.voice
        self.director = EmotionDirector(CharacterProfile())
        self.planner = SpeechPlanner(cfg)
        # Character voice registry (iron_man -> JARVIS, spider_man -> Spider-Man, etc.)
        self.current_character = normalize_character(getattr(cfg, "character", None) or "iron_man")
        # Ensure cfg.voice matches current character's reference_id for Fish
        if self.cfg.engine == "fish":
            try:
                self.cfg.voice = get_reference_id(self.current_character)
            except Exception:
                pass
        self.emotion = EmotionState(voice_id=cfg.voice)
        self.state = VOICE_OFFLINE
        self.core: TTSBackend = backend if backend is not None else build_engine_backend(cfg)
        self._first_audio = 0.0
        self._last_total = 0.0
        self._warm_sec: Optional[float] = None
        self._warm_detail = "not warmed"

    # -- provider identity ---------------------------------------------
    @property
    def provider(self) -> str:
        return self.cfg.provider or "orpheus"

    @property
    def engine_name(self) -> str:
        return self.core.name

    # -- status ---------------------------------------------------------
    def health(self) -> dict:
        ok, detail = self.core.health_check()
        return {
            "provider": self.provider,
            "engine": self.engine_name,
            "model": self.cfg.model,
            "voice": self.cfg.voice,
            "character": self.current_character,
            "character_display": get_display_name(self.current_character),
            "status": self.state,
            "available": ok,
            "detail": self._warm_detail if self._warm_detail != "not warmed" else detail,
            "warmup_s": self._warm_sec,
            "streaming": self.cfg.streaming,
            "first_audio_s": round(self._first_audio, 3),
            "last_total_s": round(self._last_total, 3),
            "emotion": self.emotion.to_dict(),
        }

    def get_current_voice(self) -> dict:
        return {
            "character": self.current_character,
            "display_name": get_display_name(self.current_character),
            "reference_id": get_reference_id(self.current_character),
            "voice": self.cfg.voice,
        }

    def set_character(self, character: str) -> bool:
        canon = normalize_character(character)
        ref = get_reference_id(canon)
        self.current_character = canon
        self.cfg.voice = ref
        # Persist character as voice_active for backwards compat
        try:
            self.cfg.save_state()
        except Exception:
            pass
        logger.info(f"[TTS] character set -> {canon} ({ref[:8]}...)")
        return True

    def warmup(self) -> tuple[bool, str]:
        """Load model once, run REAL synthesis, verify output, then READY."""
        self.state = VOICE_LOADING
        t0 = time.time()
        try:
            ok, detail = self.core.warmup()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"warmup crashed: {e}"
        self._warm_sec = round(time.time() - t0, 2)
        self._warm_detail = detail
        self.state = VOICE_READY if ok else VOICE_DEGRADED
        logger.info(f"[TTS] warmup -> {self.state} ({detail}) in {self._warm_sec}s")
        return ok, detail

    # -- controls -------------------------------------------------------
    def list_voices(self) -> list[str]:
        try:
            return self.core.list_voices()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[TTS] list_voices failed: {e}")
            return []

    def set_voice(self, vid: Optional[str]) -> bool:
        if not vid:
            return False
        known = self.list_voices()
        if known and vid not in known:
            logger.warning(f"[TTS] unknown voice {vid} (known: {known[:6]}...)")
            return False
        self.cfg.voice = vid
        self.emotion.voice_id = vid
        self.cfg.save_state()
        logger.info(f"[TTS] voice set -> {vid}")
        return True

    def set_emotion(self, emotion: Optional[str] = None, mode: Optional[str] = None,
                    intensity: Optional[float] = None):
        if mode in ("auto", "manual"):
            self.cfg.emotion_mode = mode
        from .emotion import normalize_emotion
        norm = normalize_emotion(emotion)
        if norm:
            self.cfg.emotion_default = norm
        if isinstance(intensity, (int, float)):
            self.cfg.emotion_intensity = max(0.0, min(1.0, float(intensity)))
        self.cfg.save_state()
        logger.info(f"[TTS] emotion -> mode={self.cfg.emotion_mode} "
                    f"default={self.cfg.emotion_default} intensity={self.cfg.emotion_intensity}")

    # -- core generation -----------------------------------------------
    def speak(self, text: str, character: Optional[str] = None, emotion: Optional[str] = None,
              speaking_rate: Optional[float] = None,
              priority: str = "normal") -> bytes:
        """Full pipeline -> concatenated WAV bytes (mono 16-bit PCM 24k)."""
        t0 = time.time()
        char = normalize_character(character or self.current_character)
        # Snapshot reference_id at creation time to prevent stale voice
        ref = get_reference_id(char) if self.cfg.engine == "fish" else self.cfg.voice
        cue_model = self.cfg.fish_model if self.cfg.engine == "fish" else None
        chunks = self.planner.plan(text, override_emotion=emotion,
                                   priority=priority, speaking_rate=speaking_rate,
                                   cue_model=cue_model)
        wavs = []
        first = None
        for i, ch in enumerate(chunks):
            logger.info(f"[TTS] seg {i+1}/{len(chunks)} voice={ref[:8]}... "
                        f"engine={self.engine_name} emotion={ch.emotion} "
                        f"speed={ch.speed:.2f} pitch={ch.pitch_cents} char={char}")
            wav = self.core.synthesize(ch.tts_text or ch.text, voice=ref,
                                       speed=ch.speed, pitch_cents=ch.pitch_cents)
            if first is None:
                first = time.time() - t0
            wavs.append(wav)
            self.emotion.update_from_performance(ch.performance, ref)
        if not wavs:
            raise TTSError("no audio produced")
        combined = concat_wav(wavs)
        self._last_total = time.time() - t0
        if first is not None:
            self._first_audio = first
        logger.info(f"[TTS] generated {len(combined)} bytes engine={self.engine_name} "
                    f"(first_audio {first:.2f}s, total {time.time()-t0:.2f}s)")
        return combined

    def speak_stream(self, text: str, character: Optional[str] = None, emotion: Optional[str] = None,
                     priority: str = "normal", cancel: Optional[object] = None
                     ) -> Iterator[tuple[SpeechPerformance, bytes]]:
        """Yield (SpeechPerformance, wav_bytes) per chunk as generated so the
        next chunk is synthesized while the current one is being played."""
        t0 = time.time()
        char = normalize_character(character or self.current_character)
        ref = get_reference_id(char) if self.cfg.engine == "fish" else self.cfg.voice
        cue_model = self.cfg.fish_model if self.cfg.engine == "fish" else None
        chunks = self.planner.plan(text, override_emotion=emotion, priority=priority,
                                   cue_model=cue_model)
        sent = 0
        for ch in chunks:
            stream_args = {"voice": ref, "speed": ch.speed, "pitch_cents": ch.pitch_cents}
            # Live providers may support cancellation; older/local backends
            # remain valid without that optional keyword.
            try:
                supports_cancel = "cancel" in inspect.signature(self.core.stream).parameters
            except (TypeError, ValueError):
                supports_cancel = True
            if supports_cancel:
                stream_args["cancel"] = cancel
            for rms_val, wav in self.core.stream(ch.tts_text or ch.text, **stream_args):
                if sent == 0:
                    self._first_audio = time.time() - t0
                self.emotion.update_from_performance(ch.performance, ref)
                sent += 1
                yield ch.performance, wav
        self._last_total = time.time() - t0

    def recover(self) -> tuple[bool, str]:
        """Failure recovery (§33): restart ONLY the TTS engine, reload, warm,
        verify. Does NOT restart JARVIS."""
        logger.warning("[TTS] engine recovery: re-initializing TTS only")
        try:
            self.core.shutdown()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.core = build_engine_backend(self.cfg)
            return self.warmup()
        except Exception as e:  # noqa: BLE001
            self.state = VOICE_FAILED
            return False, f"recovery failed: {e}"

    def shutdown(self):
        try:
            self.core.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.state = VOICE_OFFLINE
