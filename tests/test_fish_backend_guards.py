"""Tests for FishBackend fail-closed behavior + safe cache (§4, §14, §20)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from voice.config import VoiceConfig
from voice.fish_backend import FishBackend, _is_cacheable
from voice.tts_backend import TTSUnavailable


def _cfg(**kw):
    cfg = VoiceConfig()
    cfg.fish_api_key = "sk-test-key-1234567890"
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def test_free_model_accepted():
    b = FishBackend(_cfg(fish_model="s2.1-pro-free"))
    assert b._model == "s2.1-pro-free"


def test_unknown_model_fails_closed():
    with pytest.raises(TTSUnavailable):
        FishBackend(_cfg(fish_model="s9-turbo-billed"))


@pytest.mark.parametrize("paid", ["s2.1-pro", "s2-pro", "s1"])
def test_paid_models_blocked_without_opt_in(paid, monkeypatch):
    monkeypatch.delenv("ALLOW_PAID_FISH_MODELS", raising=False)
    with pytest.raises(TTSUnavailable):
        FishBackend(_cfg(fish_model=paid))


def test_paid_model_allowed_with_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("ALLOW_PAID_FISH_MODELS", "true")
    b = FishBackend(_cfg(fish_model="s2.1-pro"))
    assert b._model == "s2.1-pro"


def test_safe_phrases_cacheable():
    assert _is_cacheable("Hello.")
    assert _is_cacheable("I'm listening.")
    assert _is_cacheable("Voice system ready.")


def test_private_text_never_cached():
    assert not _is_cacheable("Your report shows revenue of 4 million dollars.")
    assert not _is_cacheable("Remind me to call mom at 5pm about the doctor.")
    assert not _is_cacheable("Hello. " * 20)


def test_volume_bounds():
    b = FishBackend(_cfg())
    assert b._volume_db() == 0.0
    b.cfg.fish_volume_db = 99
    assert b._volume_db() == 20.0
    b.cfg.fish_volume_db = -99
    assert b._volume_db() == -20.0


def test_request_payload_uses_free_model_and_capped_volume():
    b = FishBackend(_cfg())
    import json
    captured = {}

    class FakeResp:
        status_code = 200
        content = b"x" * 200
        text = ""

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        captured["json"] = json
        return FakeResp()

    b._session.post = fake_post
    out = b._request("Hello.", reference_id="abc123", prosody_speed=1.0)
    assert out == b"x" * 200
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    assert captured["headers"]["model"] == "s2.1-pro-free"
    assert captured["json"]["reference_id"] == "abc123"
    assert -20.0 <= captured["json"]["prosody"]["volume"] <= 20.0
