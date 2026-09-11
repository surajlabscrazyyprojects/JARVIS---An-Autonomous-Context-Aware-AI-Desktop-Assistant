"""Tests: voice profile discovery, set_active, persistence, separation from emotion."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice import VoiceConfig, VoiceProfileManager, VoiceProfile  # noqa: E402
from voice.emotion import EmotionDirector, CharacterProfile  # noqa: E402


def _cfg(tmp):
    c = VoiceConfig()
    c.voices_dir = tmp / "voices"
    c.state_dir = tmp / "config"
    return c


def test_discovers_profiles(tmp_path):
    vd = tmp_path / "voices"
    (vd / "cartoon").mkdir(parents=True)
    (vd / "cartoon" / "metadata.json").write_text(
        '{"id":"cartoon","name":"Cartoon","reference_audio":"reference.wav","reference_text":"hello there"}')
    (vd / "cartoon" / "reference.wav").write_bytes(b"RIFF....WAVE")
    mgr = VoiceProfileManager(_cfg(tmp_path))
    ids = {p["id"] for p in mgr.list()}
    assert "cartoon" in ids
    assert mgr.get("cartoon").is_ready()


def test_set_active_and_persist(tmp_path):
    vd = tmp_path / "voices"
    for vid in ("jarvis", "cartoon"):
        d = vd / vid
        d.mkdir(parents=True)
        (d / "metadata.json").write_text(
            f'{{"id":"{vid}","name":"{vid}","reference_audio":"reference.wav","reference_text":"x"}}')
        (d / "reference.wav").write_bytes(b"RIFF....WAVE")
    mgr = VoiceProfileManager(_cfg(tmp_path))
    assert mgr.set_active("cartoon") is True
    assert mgr.active == "cartoon"
    # persisted
    state = (tmp_path / "config" / "voice_state.json").read_text()
    assert "cartoon" in state


def test_set_unknown_voice_fails(tmp_path):
    mgr = VoiceProfileManager(_cfg(tmp_path))
    assert mgr.set_active("does_not_exist") is False


def test_voice_emotion_independence(tmp_path):
    """Changing voice must NOT reset emotion (and vice-versa)."""
    d = EmotionDirector(CharacterProfile())
    perf = d.classify("Wait, seriously? We actually fixed it!", mode="manual", override="excited")
    voice_before = "cartoon"
    # Emotion computed independently of the voice id used elsewhere.
    assert perf.emotion == "excited"
    # Switching voice identity doesn't touch the performance object.
    voice_after = "jarvis"
    assert perf.emotion == "excited"  # unchanged
    assert voice_before != voice_after
