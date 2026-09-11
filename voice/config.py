"""
Local expressive TTS configuration for J.A.R.V.I.S.

Fish Audio Character Voice Integration (verified standalone pattern):
  provider = "fish"      -> Fish Audio S2.1 Pro Free (https://api.fish.audio/v1/tts)
  engine   = "fish"      -> single authoritative FishTTSService
  model    = "s2.1-pro-free"

All paths derive from the project root via pathlib. Everything is overridable
through environment variables and a JSON config file (config/voice.json).
Secrets (FISH_AUDIO_API_KEY) are loaded ONLY from environment / .env, never
from committed source.

Legacy: orpheus/kokoro fields are retained for fallback/testing but Fish is
the single active pipeline.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Project root = two levels up from this file (project/voice/config.py -> project/).
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ensure project/.env is loaded for THIS process before any config is read.
# jarvis.py loads .env itself, but the standalone voice gateway (start_voice.py)
# does not, which left FISH_AUDIO_API_KEY / GROQ_API_KEY unset and the whole
# voice gateway reporting VOICE_OFFLINE. Loading here makes every entry point
# (gateway, tests, backend) see the same credentials.
try:
    from dotenv import load_dotenv

    _env_file = PROJECT_ROOT / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except Exception:  # noqa: BLE001 - dotenv optional
    pass


def _env(name: str, default=None):
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    val = _env(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    val = _env(name)
    try:
        return int(val) if val is not None else default
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    val = _env(name)
    try:
        return float(val) if val is not None else default
    except ValueError:
        return default


@dataclass
class VoiceConfig:
    # --- Active voice provider ---
    provider: str = "fish"
    engine: str = "fish"
    model: str = "s2.1-pro-free"
    voice: str = "14129c3e320149449d6bada6862f7338"  # JARVIS default
    lang_code: str = "a"               # kept for compat
    device: str = "cpu"
    offload_if_installed: bool = False

    # --- Fish Audio (verified standalone pattern) ---
    fish_api_key: str = ""             # FISH_AUDIO_API_KEY / FISH_API_KEY env
    fish_model: str = "s2.1-pro-free"
    fish_format: str = "mp3"
    fish_latency: str = "normal"       # normal | balanced
    fish_timeout: int = 30
    fish_volume_db: float = 0.0      # Fish prosody volume in dB (-20..20, 0 = unchanged)
    fish_runtime_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "runtime" / "tts_cache")
    fish_max_cache_entries: int = 128
    fish_ttl_seconds: int = 3600       # stale temp file TTL

    # --- Hume Octave (opt-in, backend-only credentials) ---
    hume_api_key: str = ""
    hume_voice_id: str = "89989d92-1de8-4e5d-97e4-23cd363e9788"
    hume_voice_provider: str = "HUME_AI"
    hume_url: str = "https://api.hume.ai/v0/tts"

    # --- Gateway (what the HUD talks to) ---
    # Localhost-only. NEVER bind to 0.0.0.0.
    tts_host: str = "127.0.0.1"
    tts_port: int = 8766

    # --- Emotion director (shared with the JARVIS character) ---
    emotion_mode: str = "auto"          # auto | manual
    emotion_default: str = "neutral"
    emotion_intensity: float = 0.75

    # --- Performance ---
    streaming: bool = True              # play chunk N while N+1 regenerates
    sentence_segmentation: bool = True  # split replies into speech-sized chunks
    interruption_enabled: bool = True   # user speech barge-in
    playback_target: str = "hud"        # hud (gateway) | system | both

    # --- Bounded short-phrase cache ---
    cache_enabled: bool = True
    cache_max_entries: int = 128

    # --- Directories (relative to project root, never absolute user paths) ---
    voices_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "voices")
    state_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "config")
    cache_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "memory" / "tts_cache")

    debug: bool = False

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "VoiceConfig":
        cfg = cls()
        # Precedence (low -> high): defaults < JSON file < persisted state < ENV
        cfg_file = PROJECT_ROOT / "config" / "voice.json"
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if not hasattr(cfg, k):
                        continue
                    if k.endswith("_dir"):
                        setattr(cfg, k, Path(v))
                    else:
                        setattr(cfg, k, v)
            except Exception:  # noqa: BLE001
                pass

        # Persisted runtime state (active voice / emotion chosen at runtime).
        state_file = cfg.state_dir / "voice_state.json"
        if state_file.exists():
            try:
                st = json.loads(state_file.read_text(encoding="utf-8"))
                if st.get("voice_active"):
                    cfg.voice = st["voice_active"]
                if st.get("emotion_mode"):
                    cfg.emotion_mode = st["emotion_mode"]
                if st.get("emotion_default"):
                    cfg.emotion_default = st["emotion_default"]
                if isinstance(st.get("emotion_intensity"), (int, float)):
                    cfg.emotion_intensity = float(st["emotion_intensity"])
            except Exception:  # noqa: BLE001
                pass

        # Environment overrides (highest priority).
        cfg.provider = _env("JARVIS_TTS_PROVIDER", cfg.provider)
        cfg.engine = _env("JARVIS_TTS_ENGINE", "hume" if cfg.provider.lower() == "hume" else cfg.engine)
        cfg.model = _env("JARVIS_TTS_MODEL", cfg.model)
        cfg.voice = _env("JARVIS_VOICE", cfg.voice)
        cfg.fish_model = _env("FISH_AUDIO_MODEL", cfg.fish_model)
        cfg.fish_model = _env("FISH_MODEL", cfg.fish_model)
        # Secure API key: FISH_AUDIO_API_KEY preferred, fallback FISH_API_KEY, then fish audio api.txt
        cfg.fish_api_key = _env("FISH_AUDIO_API_KEY", "") or _env("FISH_API_KEY", "")
        if not cfg.fish_api_key:
            # Try local file (user-provided secure file, not committed)
            fish_key_file = PROJECT_ROOT / "fish audio api.txt"
            if fish_key_file.exists():
                try:
                    cfg.fish_api_key = fish_key_file.read_text(encoding="utf-8").strip()
                except Exception:
                    pass
        cfg.hume_api_key = _env("HUME_API_KEY", "")
        cfg.hume_voice_id = _env("HUME_VOICE_ID", cfg.hume_voice_id)
        cfg.hume_voice_provider = _env("HUME_VOICE_PROVIDER", cfg.hume_voice_provider)
        cfg.hume_url = _env("HUME_TTS_URL", cfg.hume_url)
        cfg.lang_code = _env("JARVIS_TTS_LANG", cfg.lang_code)
        cfg.device = _env("JARVIS_TTS_DEVICE", cfg.device)
        cfg.tts_host = _env("JARVIS_TTS_HOST", cfg.tts_host)
        cfg.tts_port = _int("JARVIS_TTS_PORT", cfg.tts_port)
        cfg.fish_volume_db = _float("FISH_VOLUME_DB", cfg.fish_volume_db)
        cfg.emotion_mode = _env("JARVIS_EMOTION_MODE", cfg.emotion_mode)
        cfg.emotion_default = _env("JARVIS_EMOTION_DEFAULT", cfg.emotion_default)
        cfg.emotion_intensity = _float("JARVIS_EMOTION_INTENSITY", cfg.emotion_intensity)
        cfg.streaming = _bool("JARVIS_TTS_STREAMING", cfg.streaming)
        cfg.sentence_segmentation = _bool("JARVIS_TTS_SEGMENT", cfg.sentence_segmentation)
        cfg.interruption_enabled = _bool("JARVIS_TTS_INTERRUPTION", cfg.interruption_enabled)
        cfg.cache_enabled = _bool("JARVIS_TTS_CACHE", cfg.cache_enabled)
        cfg.debug = _bool("JARVIS_TTS_DEBUG", cfg.debug)

        # Ensure directories exist
        cfg.voices_dir.mkdir(parents=True, exist_ok=True)
        cfg.state_dir.mkdir(parents=True, exist_ok=True)
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        cfg.fish_runtime_dir.mkdir(parents=True, exist_ok=True)
        return cfg

    def has_fish_key(self) -> bool:
        return bool(self.fish_api_key and len(self.fish_api_key.strip()) > 10)

    def has_hume_key(self) -> bool:
        return bool(self.hume_api_key and len(self.hume_api_key.strip()) > 10)

    def fish_api_key_preview(self) -> str:
        if not self.fish_api_key:
            return "missing"
        k = self.fish_api_key.strip()
        return f"{k[:7]}...{k[-4:]}" if len(k) > 11 else "***"

    def save_state(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "voice_active": self.voice,
            "emotion_mode": self.emotion_mode,
            "emotion_default": self.emotion_default,
            "emotion_intensity": self.emotion_intensity,
        }
        (self.state_dir / "voice_state.json").write_text(
            json.dumps(state, indent=2), encoding="utf-8")

    def public(self) -> dict:
        """Config safe to expose over the API (no secrets)."""
        d = asdict(self)
        for k in list(d.keys()):
            if k.endswith("_dir"):
                d[k] = str(d[k])
        # Never expose raw API key
        if "fish_api_key" in d:
            d["fish_api_key"] = "***" if d["fish_api_key"] else ""
            d["fish_key_configured"] = self.has_fish_key()
        if "hume_api_key" in d:
            d["hume_api_key"] = "***" if d["hume_api_key"] else ""
            d["hume_key_configured"] = self.has_hume_key()
        d["tts_url"] = f"http://{self.tts_host}:{self.tts_port}"
        return d
