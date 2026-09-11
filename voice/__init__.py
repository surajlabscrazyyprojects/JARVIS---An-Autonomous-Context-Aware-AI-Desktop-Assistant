"""Local expressive TTS subsystem for J.A.R.V.I.S. (Orpheus provider / kokoro engine)."""
from __future__ import annotations

from .config import VoiceConfig, PROJECT_ROOT
from .emotion import (
    CharacterProfile, EmotionDirector, EmotionState, SpeechPerformance,
    EMOTIONS, normalize_emotion,
)
from .voice_profile import VoiceProfile, VoiceProfileManager
from .tts_backend import TTSError, TTSUnavailable
from .tts_backend import TTSBackend
from .engine import (
    VoiceEngine, build_engine_backend,
    VOICE_OFFLINE, VOICE_STARTING, VOICE_LOADING, VOICE_READY,
    VOICE_DEGRADED, VOICE_FAILED,
)
from .speech_planner import SpeechPlanner, SpeechChunk
from .speech_queue import SpeechQueue
from .audio_playback import AudioPlaybackManager, PyAudioSink, BufferSink
from .wav import encode_wav, read_wav, concat_wav, rms
from .service import VoiceService, LatencyMetrics
from .server import start_tts_server, port_in_use

__all__ = [
    "VoiceConfig", "PROJECT_ROOT",
    "CharacterProfile", "EmotionDirector", "EmotionState", "SpeechPerformance",
    "EMOTIONS", "normalize_emotion",
    "VoiceProfile", "VoiceProfileManager",
    "TTSError", "TTSUnavailable", "TTSBackend",
    "VoiceEngine", "build_engine_backend",
    "VOICE_OFFLINE", "VOICE_STARTING", "VOICE_LOADING", "VOICE_READY",
    "VOICE_DEGRADED", "VOICE_FAILED",
    "SpeechPlanner", "SpeechChunk",
    "SpeechQueue",
    "AudioPlaybackManager", "PyAudioSink", "BufferSink",
    "encode_wav", "read_wav", "concat_wav", "rms",
    "VoiceService", "LatencyMetrics",
    "start_tts_server", "port_in_use",
]