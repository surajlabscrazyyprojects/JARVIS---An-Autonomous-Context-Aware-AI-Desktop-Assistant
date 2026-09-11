"""Tests: configuration loading, env overrides, no absolute user paths."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice import VoiceConfig, PROJECT_ROOT  # noqa: E402


def test_defaults():
    c = VoiceConfig()
    assert c.provider == "fish"
    assert c.engine == "fish"
    assert c.model == "s2.1-pro-free"
    assert c.voice == "14129c3e320149449d6bada6862f7338"
    assert c.fish_model == "s2.1-pro-free"
    assert c.tts_port == 8766
    assert c.tts_host == "127.0.0.1"
    assert c.emotion_mode == "auto"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_PROVIDER", "fish")
    monkeypatch.setenv("JARVIS_TTS_ENGINE", "fish")
    monkeypatch.setenv("FISH_AUDIO_MODEL", "s2.1-pro-free")
    monkeypatch.setenv("JARVIS_TTS_PORT", "7777")
    monkeypatch.setenv("JARVIS_VOICE", "c6bfe5606e0d497586703898c87a6ac1")
    monkeypatch.setenv("JARVIS_EMOTION_INTENSITY", "0.42")
    c = VoiceConfig.load()
    assert c.provider == "fish"
    assert c.engine == "fish"
    assert c.tts_port == 7777
    assert c.voice == "c6bfe5606e0d497586703898c87a6ac1"
    assert abs(c.emotion_intensity - 0.42) < 1e-6


def test_no_absolute_user_paths():
    c = VoiceConfig.load()
    for d in (c.voices_dir, c.state_dir, c.cache_dir):
        assert d.is_absolute()
        assert str(ROOT) in str(d), "%s not under project root" % d
        assert "C:\\Users" not in str(d) or str(ROOT).startswith("C:\\Users")


def test_state_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(VoiceConfig, "load", classmethod(lambda cls: VoiceConfig()))
    c = VoiceConfig()
    c.state_dir = tmp_path / "config"
    c.voice = "am_puck"
    c.emotion_mode = "manual"
    c.emotion_intensity = 0.9
    c.save_state()
    again = VoiceConfig()
    again.state_dir = tmp_path / "config"
    state_file = again.state_dir / "voice_state.json"
    assert state_file.exists()
    import json
    st = json.loads(state_file.read_text())
    assert st["voice_active"] == "am_puck"
    assert st["emotion_mode"] == "manual"
