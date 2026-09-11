"""
Fish Audio backend â€” verified standalone pattern.

Endpoint: https://api.fish.audio/v1/tts
Headers: Authorization: Bearer <FISH_AUDIO_API_KEY>, Content-Type: application/json, model: s2.1-pro-free
Payload: {text, reference_id, format: mp3, prosody: {speed, volume, normalize_loudness}, normalize: true, latency: normal}

One authoritative FishTTSService will use this backend.
Secrets are NEVER logged. Temp MP3s are cleaned immediately after playback.
"""
from __future__ import annotations

import os
import time
import uuid
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Iterator, Optional, Tuple

import requests

from .character_registry import get_reference_id, normalize_character
from .config import VoiceConfig, PROJECT_ROOT
from .log import logger
from .tts_backend import TTSBackend, TTSError, TTSUnavailable
from .wav import encode_wav

try:
    import numpy as np
except Exception:
    np = None

FISH_URL = "https://api.fish.audio/v1/tts"
DEFAULT_MODEL = "s2.1-pro-free"

# Phrases safe to cache by default (deterministic, non-private). Everything
# else bypasses the cache so private user-specific responses are never stored.
_SAFE_CACHE_RE = None

def _safe_cache_patterns():
    global _SAFE_CACHE_RE
    if _SAFE_CACHE_RE is None:
        import re as _re
        pats = [
            r"^(yes|no|okay|ok|sure|done|thanks|thank you|hello|hi|hey|good (morning|evening|night)|"
            r"you'?re welcome|goodbye|bye|listening|sorry|understood|confirmed|ready|standing by|"
            r"voice system ready|i'?m listening)\.?$",
        ]
        _SAFE_CACHE_RE = _re.compile("|".join(f"(?:{p})" for p in pats), _re.I)
    return _SAFE_CACHE_RE


def _is_cacheable(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or len(t.split()) > 8:
        return False
    return bool(_safe_cache_patterns().match(t))


# Prosody mapping for Fish (only speed/volume are supported)
_EMOTION_SPEED = {
    "neutral": 1.0, "calm": 0.95, "happy": 1.06, "excited": 1.14,
    "very_excited": 1.22, "amused": 1.06, "curious": 1.04, "surprised": 1.10,
    "confident": 1.02, "supportive": 0.97, "empathetic": 0.92, "sad": 0.88,
    "serious": 0.94, "tired": 0.85, "bored": 0.90, "frustrated": 1.08,
    "relieved": 0.98, "celebratory": 1.18,
}

def _speed_for_emotion(emotion: Optional[str], intensity: float = 0.75) -> float:
    if not emotion:
        return 1.0
    base = _EMOTION_SPEED.get(emotion.lower(), 1.0)
    # intensity scales the delta from 1.0
    frac = 0.6 + 0.4 * max(0.0, min(1.0, intensity))
    return max(0.7, min(1.4, 1.0 + (base - 1.0) * frac))

def _is_mp3(data: bytes) -> bool:
    return data[:3] == b"ID3" or data[:2] == b"\xff\xfb" or data[:2] == b"\xff\xf3" or data[:4] == b"RIFF" and b"mp3" in data[:20].lower()

class FishBackend(TTSBackend):
    name = "fish"

    def __init__(self, cfg: VoiceConfig):
        self.cfg = cfg
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "JARVIS-FishTTS/1.0"})
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._warmed = False
        # Secure: load key without logging value
        self._api_key = (cfg.fish_api_key or "").strip()
        if not self._api_key:
            # Try fish audio api.txt fallback (already handled in config, but double-check)
            p = PROJECT_ROOT / "fish audio api.txt"
            if p.exists():
                try:
                    self._api_key = p.read_text(encoding="utf-8").strip()
                except Exception:
                    pass
        self._model = getattr(cfg, "fish_model", None) or getattr(cfg, "model", DEFAULT_MODEL)
        # Fail-closed model validation (§4): unknown or paid-without-opt-in
        # models raise here — we never send a request Fish could bill.
        self._model = self._validate_model(self._model)
        # Temp dir
        self._tmp_dir = getattr(cfg, "fish_runtime_dir", PROJECT_ROOT / "runtime" / "tts_cache")
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_stale_startup()

    def _cleanup_stale_startup(self):
        # Remove stale jarvis_tts_*.mp3 on startup
        try:
            now = time.time()
            ttl = getattr(self.cfg, "fish_ttl_seconds", 3600)
            for p in self._tmp_dir.glob("jarvis_tts_*.mp3"):
                try:
                    if now - p.stat().st_mtime > ttl:
                        p.unlink(missing_ok=True)
                except Exception:
                    pass
            # Also clean old fish_test_output.mp3 if present in project root
            for p in [PROJECT_ROOT / "fish_test_output.mp3"]:
                if p.exists():
                    try:
                        if now - p.stat().st_mtime > ttl:
                            p.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            pass

    @staticmethod
    def _validate_model(model: str) -> str:
        """Fail-closed: only s2.1-pro-free by default; paid needs explicit opt-in."""
        from .fish_config import FREE_MODEL, KNOWN_MODELS
        m = (model or "").strip() or FREE_MODEL
        if m not in KNOWN_MODELS:
            raise TTSUnavailable(
                f"Fish model {m!r} unknown — blocked (Fish bills unrecognized "
                f"models as paid). Use '{FREE_MODEL}'.")
        if m != FREE_MODEL:
            import os as _os
            if _os.environ.get("ALLOW_PAID_FISH_MODELS", "").strip().lower() not in ("1", "true", "yes", "on"):
                raise TTSUnavailable(
                    f"Fish model {m!r} is paid and ALLOW_PAID_FISH_MODELS is not set — "
                    f"blocked. Use '{FREE_MODEL}'.")
            logger.warning(f"[TTS] PAID Fish model {m!r} explicitly enabled")
        return m

    def _volume_db(self) -> float:
        try:
            return max(-20.0, min(20.0, float(getattr(self.cfg, "fish_volume_db", 0.0))))
        except (TypeError, ValueError):
            return 0.0

    def _has_key(self) -> bool:
        return bool(self._api_key and len(self._api_key) > 10)

    def health_check(self) -> Tuple[bool, str]:
        if not self._has_key():
            return False, "FISH_AUDIO_API_KEY missing (set FISH_AUDIO_API_KEY or FISH_API_KEY)"
        if not self._model:
            return False, "model not configured"
        # Light check: key format
        if not self._api_key.startswith("sk-"):
            return False, "API key format invalid"
        if self._warmed:
            return True, "ready (warm)"
        return True, "key configured (not yet warmed)"

    def warmup(self) -> Tuple[bool, str]:
        try:
            # Use JARVIS voice for warmup
            ref = get_reference_id("iron_man")
            mp3 = self._request("Voice system ready.", reference_id=ref, prosody_speed=1.0)
            if not mp3 or len(mp3) < 100:
                return False, "warmup returned empty audio"
            # Verify decode
            wav = self._mp3_to_wav_bytes(mp3)
            if len(wav) < 44:
                return False, "warmup decode failed"
            # Verify temp playback path without leaving file
            tmp = self._write_temp_mp3(mp3)
            try:
                if not tmp.exists() or tmp.stat().st_size < 100:
                    return False, "warmup temp file failed"
            finally:
                self._delete_temp(tmp)
            self._warmed = True
            return True, "ready (synthesis verified)"
        except Exception as e:
            # Never expose key in error
            msg = str(e)
            if self._api_key and self._api_key in msg:
                msg = msg.replace(self._api_key, "***")
            return False, f"warmup failed: {msg[:200]}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "model": self._model,
        }

    def _request(self, text: str, reference_id: str, prosody_speed: float = 1.0) -> bytes:
        if not self._has_key():
            raise TTSUnavailable("FISH_AUDIO_API_KEY not configured")
        if not text or not text.strip():
            raise TTSError("empty text")
        if not reference_id:
            raise TTSError("reference_id missing")
        payload = {
            "text": text,
            "reference_id": reference_id,
            "format": "mp3",
            "prosody": {
                "speed": float(prosody_speed),
                "volume": self._volume_db(),
                "normalize_loudness": True,
            },
            "normalize": True,
            "latency": "normal",
        }
        timeout = getattr(self.cfg, "fish_timeout", 30)
        try:
            resp = self._session.post(
                FISH_URL,
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
        except requests.Timeout:
            raise TTSError(f"Fish request timeout after {timeout}s")
        except requests.RequestException as e:
            raise TTSError(f"Fish network error: {e.__class__.__name__}")
        if resp.status_code == 401:
            raise TTSUnavailable("Fish authentication failed (401) - check API key")
        if resp.status_code == 403:
            raise TTSUnavailable("Fish forbidden (403) - check voice ID / model")
        if resp.status_code in (400, 404) and "Reference not found" in resp.text:
            # Fallback to JARVIS voice if the specific character voice is missing/deleted
            fallback = "14129c3e320149449d6bada6862f7338"
            if reference_id != fallback:
                logger.warning(f"[TTS] Fish reference {reference_id[:8]} not found, falling back to JARVIS")
                # Retry once with JARVIS
                payload["reference_id"] = fallback
                try:
                    resp = self._session.post(FISH_URL, headers=self._headers(), json=payload, timeout=timeout)
                except Exception:
                    pass
                if resp.status_code == 200 and resp.content and len(resp.content) >= 100:
                    return resp.content
            raise TTSError(f"Fish voice not found for {reference_id[:8]}...")
        if resp.status_code == 404:
            raise TTSError(f"Fish voice/model not found (404) for {reference_id[:8]}...")
        if resp.status_code == 429:
            raise TTSError("Fish rate limited (429)")
        if resp.status_code != 200:
            body = resp.text[:300].replace(self._api_key, "***") if self._api_key in resp.text else resp.text[:300]
            raise TTSError(f"Fish HTTP {resp.status_code}: {body}")
        if not resp.content or len(resp.content) < 100:
            raise TTSError("Fish returned empty audio")
        return resp.content

    def _mp3_to_wav_bytes(self, mp3: bytes) -> bytes:
        # Use pydub + ffmpeg to decode MP3 -> PCM -> WAV, fallback to soundfile
        # Try pydub first (needs ffmpeg, which is available)
        try:
            from pydub import AudioSegment
            import io
            seg = AudioSegment.from_file(io.BytesIO(mp3), format="mp3")
            # Normalize to 24000 mono for consistent playback
            seg = seg.set_channels(1).set_frame_rate(24000)
            buf = io.BytesIO()
            seg.export(buf, format="wav")
            return buf.getvalue()
        except Exception:
            pass
        # Fallback: try soundfile
        try:
            import soundfile as sf
            import io
            import numpy as np
            data, sr = sf.read(io.BytesIO(mp3))
            # Convert to mono 24000 WAV
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            buf = io.BytesIO()
            sf.write(buf, data, 24000, format='WAV')
            return buf.getvalue()
        except Exception:
            pass
        # Last resort: return mp3 as-is (caller may handle via temp file playback)
        return mp3

    def _write_temp_mp3(self, mp3: bytes) -> Path:
        name = f"jarvis_tts_{uuid.uuid4().hex}.mp3"
        p = self._tmp_dir / name
        p.write_bytes(mp3)
        return p

    def _delete_temp(self, path: Path):
        try:
            if path and path.exists() and path.name.startswith("jarvis_tts_"):
                path.unlink(missing_ok=True)
        except Exception:
            pass

    def _cleanup_old_temps(self):
        try:
            now = time.time()
            ttl = getattr(self.cfg, "fish_ttl_seconds", 3600)
            for p in self._tmp_dir.glob("jarvis_tts_*.mp3"):
                if now - p.stat().st_mtime > ttl:
                    p.unlink(missing_ok=True)
        except Exception:
            pass

    def _pcm_to_wav(self, pcm: bytes, sample_rate: int = 24000) -> bytes:
        """Wrap raw Fish PCM bytes (mono 16-bit LE) as a WAV so the rest of the
        pipeline that expects WAV stays unchanged."""
        from .wav import encode_wav
        import numpy as np
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.int16)
        return encode_wav(arr, sample_rate=sample_rate)

    # --- TTSBackend interface ---
    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0, pitch_cents: int = 0) -> bytes:
        # voice may be character name or reference_id
        ref = None
        if voice and len(voice) >= 30 and all(c in "0123456789abcdef" for c in voice.lower()):
            ref = voice
        else:
            # Treat voice as character, fallback to iron_man
            ref = get_reference_id(voice or "iron_man")
        # Cache ONLY safe deterministic short phrases (privacy default:
        # private user-specific responses are never stored).
        cache_key = f"{ref}:{speed:.2f}:{hash(text)}:{len(text)}"
        cacheable = len(text.split()) <= 6 and _is_cacheable(text)
        if cacheable:
            with self._lock:
                hit = self._cache.get(cache_key)
                if hit is not None:
                    self._cache.move_to_end(cache_key)
                    return hit
        mp3 = self._request(text, reference_id=ref, prosody_speed=float(speed))
        # Temp file lifecycle: write -> decode -> delete (spec Â§10-11)
        tmp = None
        try:
            tmp = self._write_temp_mp3(mp3)
            wav = self._mp3_to_wav_bytes(mp3)
            out = wav if wav[:4] == b"RIFF" else mp3
        finally:
            if tmp is not None:
                self._delete_temp(tmp)
        if cacheable:
            with self._lock:
                self._cache[cache_key] = out
                while len(self._cache) > getattr(self.cfg, "fish_max_cache_entries", 128):
                    self._cache.popitem(last=False)
        # Periodic TTL cleanup
        if len(self._cache) % 20 == 0:
            self._cleanup_old_temps()
        return out

    def stream(self, text: str, voice: Optional[str] = None, speed: float = 1.0, pitch_cents: int = 0,
               cancel: "threading.Event | None" = None) -> Iterator[Tuple[float, bytes]]:
        """One logical Fish live stream for the whole response (no per-word API
        calls, §5). Falls back to per-segment HTTP when WS/live is unavailable.
        Each yielded WAV is ordered and tied to the caller's generation ID via
        the stream wrapper in VoiceService."""
        from .preprocess import segment_sentences
        try:
            segs = segment_sentences(text) if getattr(self.cfg, "sentence_segmentation", True) else [text]
        except Exception:
            segs = [text]
        segs = [s for s in segs if s and s.strip()]
        if not segs:
            return
        ref = None
        if voice and len(voice) >= 30 and all(c in "0123456789abcdef" for c in voice.lower()):
            ref = voice
        else:
            ref = get_reference_id(voice or "iron_man")
        # Prefer verified live WS (one stream, chunked PCM, lowest TTFA).
        try:
            from .fish_live import FishLiveSession
            from .fish_config import FishConfig as _FC
            live_cfg = _FC.from_env()
            # Reuse the FishBackend's key/reference/model so spec §4 precedence
            # (FISH_* vs fish audio api.txt) is honored in-process.
            live_cfg.api_key = self._api_key
            live_cfg.reference_id = ref
            live_cfg.model = self._model
            live_cfg.validate()
            sess = FishLiveSession(live_cfg, reference_id=ref, speed=float(speed),
                                   cancel=cancel)
            # Segmenter already produced natural phrase boundaries; stream them
            # as TextEvents on ONE session so the voice stays consistent.
            def _chunks():
                for s in segs:
                    yield s
            pcm_buf = b""
            chunk_idx = 0
            for pcm in sess.synthesize(_chunks()):
                pcm_buf += pcm
                # Flush every ~0.6s of PCM (24000*0.6*2 bytes) so playback can
                # start before the full answer is done.
                if len(pcm_buf) >= 28800:
                    wav = self._pcm_to_wav(pcm_buf)
                    chunk_idx += 1
                    try:
                        from .wav import rms as _rms
                        amp = _rms(wav)
                    except Exception:
                        amp = 0.5
                    pcm_buf = b""
                    yield amp, wav
            if pcm_buf:
                wav = self._pcm_to_wav(pcm_buf)
                try:
                    from .wav import rms as _rms
                    amp = _rms(wav)
                except Exception:
                    amp = 0.5
                yield amp, wav
            # Live path succeeded — use its connect/first-audio timings for metrics.
            try:
                self._last_live_connect_ms = sess.t_connect_ms
                self._last_live_first_ms = sess.t_first_audio_ms
            except Exception:
                pass
            return
        except Exception as e:  # noqa: BLE001
            # Common during tests or offline — fall through to HTTP segments.
            logger.info(f"[TTS] live stream unavailable/fallback ({e.__class__.__name__}): {str(e)[:120]} — using HTTP segments")
        for seg in segs:
            wav = self.synthesize(seg, voice=voice, speed=speed, pitch_cents=pitch_cents)
            try:
                from .wav import rms
                amp = rms(wav)
            except Exception:
                amp = 0.5
            if cancel is not None and cancel.is_set():
                return
            yield amp, wav

    def list_voices(self) -> list[str]:
        # Return character display names + reference_ids for debugging
        from .character_registry import list_characters
        chars = list_characters()
        return [f"{k}:{v['reference_id'][:8]}" for k, v in chars.items()]

    def stop(self) -> None:
        # No persistent generation to stop at backend level; handled by service queue
        pass

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def shutdown(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass
        self._cache.clear()
        self._warmed = False
        self._cleanup_old_temps()

