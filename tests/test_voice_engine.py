"""
Voice engine test suite (no model required — unit-level, fast).

Covers the expressive layer the specification demands:
  A. Emotional contrast across different situations
  B. Expressive variety across 20+ utterances
  C. Deterministic consistency for repeated identical input
  D. Contextual paralinguistic tags only (never injected blindly)
  E. Long-text fragmentation / dramatic pacing
  F. Reaction prefaces only when the state justifies them
plus interruption semantics, serialized synthesis, WAV encoding and the
local TTS HTTP endpoint.
"""

from __future__ import annotations

import io
import json
import struct
import threading
import time
import wave

import numpy as np
import pytest

from jarvis.voice.audio import tensor_to_wav_bytes
from jarvis.voice.character import JARVIS_CHARACTER
from jarvis.voice.chatterbox_engine import ChatterboxNanoEngine
from jarvis.voice.config import VoiceEngineConfig, load_voice_config
from jarvis.voice.emotion import CharacterEmotionEngine, EmotionalState
from jarvis.voice.engine import VoiceEngine, VoiceEngineManager
from jarvis.voice.exceptions import (
    VoiceInitError,
    VoiceNotReadyError,
    VoiceSynthesisError,
)
from jarvis.voice.prosody import plan_performance
from jarvis.voice.text_preprocessor import TextPreprocessor
from jarvis.voice.tts_server import VoiceTTSServer, create_tts_server


def make_state(**kw) -> EmotionalState:
    return EmotionalState(**kw)


def make_preprocessor(seed: int = 42) -> TextPreprocessor:
    return TextPreprocessor(character=JARVIS_CHARACTER, seed=seed)


def make_engine(character: str = "IRON_MAN") -> CharacterEmotionEngine:
    spec = JARVIS_CHARACTER if isinstance(character, str) else character
    return CharacterEmotionEngine(character=spec)


# ---------------------------------------------------------------------------
# A. Emotional contrast
# ---------------------------------------------------------------------------

def test_emotional_contrast_success_vs_failure():
    engine = make_engine()
    text = "The reactor is stable, sir. All systems report nominal output."

    success = engine.update(text, system_event="SUCCESS")
    engine.reset()
    failure = engine.update(text, system_event="FAILURE")

    assert success.energy > failure.energy
    assert success.happiness > failure.happiness
    assert failure.seriousness > success.seriousness
    assert success.happiness - failure.happiness > 0.02


def test_emotional_contrast_dramatic_vs_calm():
    engine = make_engine()
    calm = engine.update("I am simply running a routine check, sir.")
    engine.reset()
    dramatic = engine.update("The arc reactor is going critical. Every second matters.")

    assert dramatic.energy > calm.energy
    assert dramatic.dramatic_intensity > calm.dramatic_intensity
    profile_calm = plan_performance(calm, "I am simply running a routine check, sir.")
    profile_dramatic = plan_performance(dramatic, "The arc reactor is going critical. Every second matters.")
    assert profile_dramatic.pace > profile_calm.pace or profile_dramatic.dramatic_timing > profile_calm.dramatic_timing


def test_emotional_contrast_delightful_success_boosts_playfulness():
    engine = make_engine()
    state = engine.update("It worked, sir. The sequence executed perfectly.",
                          system_event="DELIGHTFUL_SUCCESS")
    assert state.happiness > 0.5
    assert state.excitement > 0.5


# ---------------------------------------------------------------------------
# B. Expressive variety across utterances
# ---------------------------------------------------------------------------

UTTERANCES = [
    "The diagnostics are complete, sir. Everything checks out.",
    "I would advise caution before proceeding with that.",
    "Absolutely brilliant, sir. The payload executed flawlessly.",
    "Sir, I detect an anomaly in sector seven.",
    "Who do you think I am, sir? I am quite capable of multitasking.",
    "My apologies. Let me correct that immediately.",
    "The coffee is brewing, sir. Two sugars, as requested.",
    "I took the liberty of rescheduling your afternoon.",
    "Interesting. The data suggests a pattern I did not anticipate.",
    "Your wit remains unmatched, sir. I do try to keep up.",
    "Critical failure detected in the power coupling.",
    "May I suggest a different approach, sir?",
    "The simulation ran in under three minutes.",
    "Yes, sir. The house is secure. All doors are locked.",
    "I am afraid the news is not good, sir.",
    "Stark Industries stock is up another four percent.",
    "Shall I prepare the suit for launch, sir?",
    "That is the third time this week you have asked.",
    "Consider it done. The files are already encrypted.",
    "I have nothing further to report, sir.",
    "Very well. Proceeding with the ignition sequence.",
    "You always say that, and yet here we are again.",
]


def test_expressive_variety_across_utterances():
    engine = make_engine()
    profiles = set()
    for text in UTTERANCES:
        state = engine.update(text)
        profile = plan_performance(state, text)
        profiles.add((round(profile.pace, 3), round(profile.pause_density, 3)))
    assert len(profiles) >= 8, "expected varied delivery across 22 utterances"


def test_repeated_identical_utterance_is_stable():
    engine = make_engine()
    text = UTTERANCES[0]
    engine.update(text)
    s1 = engine.state
    s2 = engine.update(text)
    assert 0.0 <= s2.energy <= 1.0
    assert abs(s2.energy - s1.energy) < 0.25
    assert abs(s2.seriousness - s1.seriousness) < 0.25


# ---------------------------------------------------------------------------
# C. Deterministic consistency
# ---------------------------------------------------------------------------

def test_consistency_same_input_same_profile():
    engine = make_engine()
    text = "The reactor is stable, sir. All systems nominal."
    engine.update(text)
    s1 = engine.state
    profile1 = plan_performance(s1, text)
    engine.update(text)
    s2 = engine.state
    profile2 = plan_performance(s2, text)
    assert profile1 == profile2


def test_consistency_preprocessor_same_seed():
    pp1 = make_preprocessor(seed=7)
    pp2 = make_preprocessor(seed=7)
    text = "Excellent, sir. The tests passed without a single issue."
    state = make_state(energy=0.8, happiness=0.8, excitement=0.7, playfulness=0.7)
    profile = plan_performance(state, text)
    assert pp1.preprocess(text, state, profile) == pp2.preprocess(text, state, profile)


# ---------------------------------------------------------------------------
# D. Contextual paralinguistic tags
# ---------------------------------------------------------------------------

def test_laugh_signal_injects_supported_tag():
    pp = make_preprocessor()
    state = make_state(happiness=0.85, excitement=0.8, playfulness=0.7)
    profile = plan_performance(state, "That is hilarious, sir. haha")
    out = pp.preprocess("That is hilarious, sir. haha", state, profile)
    assert "[chuckle]" in out or "[laugh]" in out


def test_no_tag_when_not_warranted():
    pp = make_preprocessor()
    state = make_state(seriousness=0.9, energy=0.3, happiness=0.2)
    profile = plan_performance(state, "Sir, the containment breach is severe.")
    out = pp.preprocess("Sir, the containment breach is severe.", state, profile)
    assert "[laugh]" not in out
    assert "[chuckle]" not in out


def test_unsupported_groq_cues_are_removed():
    pp = make_preprocessor()
    state = make_state()
    profile = plan_performance(state, "text")
    raw = "I am terribly sorry, sir. [heavy sigh] The system needs repair. [voice trembling]"
    out = pp.preprocess(raw, state, profile)
    assert "[heavy sigh]" not in out
    assert "[voice trembling]" not in out
    assert "sorry" in out


def test_known_cue_maps_to_supported_tag():
    pp = make_preprocessor()
    state = make_state(playfulness=0.6)
    profile = plan_performance(state, "text")
    out = pp.preprocess("Right, sir. [clears throat] As I was saying.", state, profile)
    assert "[clear throat]" in out


def test_emoji_never_reaches_tts_text():
    pp = make_preprocessor()
    state = make_state()
    profile = plan_performance(state, "text")
    out = pp.preprocess("All clear, sir 😂👌", state, profile)
    assert "😂" not in out


def test_markdown_and_colons_cleaned():
    pp = make_preprocessor()
    state = make_state()
    profile = plan_performance(state, "text")
    out = pp.preprocess("**Result**: 42 — see `report`: done.", state, profile)
    assert "**" not in out
    assert "`" not in out
    assert ":" not in out


def test_existing_laugh_tag_not_duplicated():
    pp = make_preprocessor()
    state = make_state(happiness=0.9, excitement=0.85, playfulness=0.8)
    profile = plan_performance(state, "That is hilarious. [laugh] Really, sir.")
    out = pp.preprocess("That is hilarious. [laugh] Really, sir.", state, profile)
    assert out.count("[laugh]") <= 1


# ---------------------------------------------------------------------------
# E. Long-text fragmentation / dramatic pacing
# ---------------------------------------------------------------------------

LONG_CALM = (
    "Sir, I have compiled the complete analysis of the quarterly production "
    "cycle and the projected maintenance schedule for the next twelve months. "
    "The efficiency metrics show a modest improvement across the assembly "
    "floor, and the new reactor core is performing within expected parameters. "
    "I have also prepared a full report for your review, which details every "
    "individual subsystem along with recommended interventions and expected "
    "downtime windows for each of the proposed upgrades."
)


def test_long_text_fragments():
    state = make_state(energy=0.4, calm=0.8)
    profile = plan_performance(state, LONG_CALM)
    assert profile.fragmentation > 0.4


def test_dramatic_reveal_uses_ellipsis():
    pp = make_preprocessor()
    state = make_state(dramatic_intensity=0.85, energy=0.6)
    profile = plan_performance(state, "I have completed the scan. The target is here.")
    assert profile.dramatic_timing > 0.5
    out = pp.preprocess("I have completed the scan. The target is here.", state, profile)
    assert "..." in out


def test_short_plain_sentence_no_pause_noise():
    pp = make_preprocessor()
    state = make_state(energy=0.5)
    profile = plan_performance(state, "All systems nominal, sir.")
    out = pp.preprocess("All systems nominal, sir.", state, profile)
    assert out.count("...") <= 1


# ---------------------------------------------------------------------------
# F. Reaction prefaces
# ---------------------------------------------------------------------------

def test_reaction_preface_only_when_surprised():
    pp = make_preprocessor(seed=1)
    shocked = make_state(surprise=0.95, dramatic_intensity=0.8)
    profile = plan_performance(shocked, "You want me to do what?")
    out = pp.preprocess("You want me to do what?", shocked, profile)
    assert out.startswith(tuple(JARVIS_CHARACTER.reactions))


def test_no_reaction_for_plain_state():
    pp = make_preprocessor(seed=1)
    state = make_state(energy=0.5, surprise=0.2)
    profile = plan_performance(state, "The system is operational, sir.")
    out = pp.preprocess("The system is operational, sir.", state, profile)
    assert not out.startswith(tuple(JARVIS_CHARACTER.reactions))


# ---------------------------------------------------------------------------
# Interruption / serialization semantics
# ---------------------------------------------------------------------------

class FakeEngine(VoiceEngine):
    name = "fake-engine"

    def __init__(self, fail: bool = False, delay: float = 0.0) -> None:
        self.fail = fail
        self.delay = delay
        self.ready = False
        self.calls = 0

    def initialize(self) -> None:
        self.ready = True

    def is_ready(self) -> bool:
        return self.ready

    def synthesize(self, text: str, **kwargs) -> bytes:
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        if self.delay:
            time.sleep(self.delay)
        return make_sine_wav()

    def shutdown(self) -> None:
        self.ready = False


def make_sine_wav(duration: float = 0.5, sr: int = 24000) -> bytes:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    samples = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return tensor_to_wav_bytes(samples[None, :], sr)


def test_manager_not_ready_raises():
    mgr = VoiceEngineManager(VoiceEngineConfig(), FakeEngine())
    with pytest.raises(VoiceNotReadyError):
        mgr.synthesize("hello")


def test_manager_wraps_engine_errors():
    mgr = VoiceEngineManager(VoiceEngineConfig(), FakeEngine(fail=True))
    mgr.initialize()
    with pytest.raises(VoiceSynthesisError):
        mgr.synthesize("hello")


def test_manager_serializes_concurrent_synthesis():
    mgr = VoiceEngineManager(VoiceEngineConfig(), FakeEngine(delay=0.2))
    mgr.initialize()
    results: list[bytes] = []
    errors: list[Exception] = []

    def worker():
        try:
            results.append(mgr.synthesize("hello"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == 4
    assert mgr.engine.calls == 4


def test_manager_records_metrics():
    mgr = VoiceEngineManager(VoiceEngineConfig(), FakeEngine())
    mgr.initialize()
    mgr.synthesize("hello")
    assert mgr.metrics.synthesis_count == 1
    assert mgr.metrics.average_synthesis_seconds > 0
    assert mgr.metrics.rtf > 0


def test_interruption_shutdown_then_reinit():
    mgr = VoiceEngineManager(VoiceEngineConfig(), FakeEngine())
    mgr.initialize()
    assert mgr.is_ready()
    mgr.shutdown()
    assert not mgr.is_ready()
    with pytest.raises(VoiceNotReadyError):
        mgr.synthesize("hello")


# ---------------------------------------------------------------------------
# WAV encoding
# ---------------------------------------------------------------------------

def test_tensor_to_wav_bytes_valid_wav():
    sr = 24000
    wav = make_sine_wav(duration=1.0, sr=sr)
    with wave.open(io.BytesIO(wav), "rb") as f:
        assert f.getframerate() == sr
        assert f.getnchannels() == 1
        assert f.getsampwidth() == 2
        assert abs(f.getnframes() / sr - 1.0) < 0.01


def test_wav_peak_normalized():
    sr = 24000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    quiet = (1e-4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav = tensor_to_wav_bytes(quiet[None, :], sr)
    with wave.open(io.BytesIO(wav), "rb") as f:
        pcm = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    peak = np.max(np.abs(pcm)) / 32767.0
    assert peak > 0.5, "quiet input must be peak-normalized"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_env_overrides(monkeypatch):
    monkeypatch.setenv("VOICE_ENGINE", "chatterbox-turbo")
    monkeypatch.setenv("VOICE_HTTP_PORT", "9999")
    monkeypatch.setenv("VOICE_MAX_TEXT_CHARS", "777")
    cfg = load_voice_config({})
    assert cfg.engine == "chatterbox-turbo"
    assert cfg.http_port == 9999
    assert cfg.max_text_chars == 777


def test_config_settings_voice_dict(monkeypatch):
    monkeypatch.delenv("VOICE_ENGINE", raising=False)
    cfg = load_voice_config({"tts": {"engine": "chatterbox-nano", "temperature": 0.9}})
    assert cfg.engine == "chatterbox-nano"
    assert cfg.temperature == 0.9


def test_config_invalid_engine_raises(monkeypatch):
    monkeypatch.setenv("VOICE_ENGINE", "skynet")
    with pytest.raises(VoiceInitError):
        load_voice_config({})


def test_config_default_reference_resolution():
    cfg = VoiceEngineConfig()
    path = cfg.reference_path()
    assert path.is_absolute()
    assert path.name == "jarvis_reference.wav"


# ---------------------------------------------------------------------------
# Local TTS HTTP endpoint (fake engine, no model)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tts_server():
    cfg = VoiceEngineConfig()
    cfg.http_port = 0  # ephemeral — never collide with the live agent's TTS port (8766)
    mgr = VoiceEngineManager(cfg, FakeEngine())
    mgr.initialize()
    server = create_tts_server(mgr, cfg)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _post(server: VoiceTTSServer, path: str, payload: dict | None = None) -> tuple[int, bytes, dict]:
    import urllib.request

    host, port = server.server_address
    url = f"http://{host}:{port}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def test_health_endpoint(tts_server):
    status, body, _ = _post(tts_server, "/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["status"] == "ok"
    assert payload["ready"] is True
    assert payload["engine"] == "fake-engine"


def test_tts_endpoint_returns_wav(tts_server):
    status, body, headers = _post(tts_server, "/tts", {"text": "Hello sir, all systems online."})
    assert status == 200
    assert headers["Content-Type"] == "audio/wav"
    assert headers.get("Access-Control-Allow-Origin") == "*"
    with wave.open(io.BytesIO(body), "rb") as f:
        assert f.getframerate() == 24000


def test_tts_endpoint_empty_text_400(tts_server):
    status, body, _ = _post(tts_server, "/tts", {"text": "   "})
    assert status == 400


def test_tts_endpoint_invalid_json_400(tts_server):
    import urllib.request

    host, port = tts_server.server_address
    req = urllib.request.Request(
        f"http://{host}:{port}/tts", data=b"{not json", method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_tts_endpoint_unknown_route_404(tts_server):
    status, _, _ = _post(tts_server, "/nope")
    assert status == 404


def test_tts_endpoint_cors_preflight(tts_server):
    import urllib.request

    host, port = tts_server.server_address
    req = urllib.request.Request(
        f"http://{host}:{port}/tts", data=b"", method="OPTIONS"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_character_energy_scales_expressiveness():
    from jarvis.voice.character import CharacterSpec

    low = CharacterSpec(character_id="LOW", character_energy=0.3,
                        character_playfulness=0.3, character_expressiveness=0.3)
    high = CharacterSpec(character_id="HIGH", character_energy=0.9,
                         character_playfulness=0.9, character_expressiveness=0.9)
    e_low = CharacterEmotionEngine(character=low)
    e_high = CharacterEmotionEngine(character=high)
    text = "The suit is ready, sir. Shall we take flight?"
    s_low = e_low.update(text)
    s_high = e_high.update(text)
    assert s_high.energy > s_low.energy
    assert s_high.playfulness > s_low.playfulness
    assert s_high.expressiveness() > s_low.expressiveness()


def test_character_spec_reactions_unique():
    from jarvis.voice.character import CharacterSpec

    spec = CharacterSpec()
    assert len(spec.reactions) == len(set(spec.reactions))
    assert len(spec.reactions) >= 5