"""Tests for fail-closed Fish configuration (§4, §20). No API key needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from voice.fish_config import FREE_MODEL, FishConfig, FishConfigError


def _env(**kw):
    base = {"FISH_API_KEY": "sk-test-key-1234567890", "FISH_REFERENCE_ID": "abc123ref"}
    base.update(kw)
    return base


def test_free_model_accepted():
    cfg = FishConfig.from_env(_env())
    assert cfg.model == FREE_MODEL
    assert cfg.is_free_mode


def test_missing_key_fails_closed():
    with pytest.raises(FishConfigError):
        FishConfig.from_env({"FISH_REFERENCE_ID": "abc123ref"})


def test_missing_reference_fails_closed():
    with pytest.raises(FishConfigError):
        FishConfig.from_env({"FISH_API_KEY": "sk-test-key-1234567890"})


def test_missing_model_defaults_to_free():
    # Unset/empty FISH_MODEL safely defaults to the free model (per §4 default
    # config); malformed or paid values below still fail closed.
    cfg = FishConfig.from_env({"FISH_API_KEY": "sk-k", "FISH_REFERENCE_ID": "r", "FISH_MODEL": ""})
    assert cfg.model == FREE_MODEL


def test_unknown_model_rejected():
    with pytest.raises(FishConfigError):
        FishConfig.from_env(_env(FISH_MODEL="s9-ultra WoW"))


@pytest.mark.parametrize("paid", ["s2.1-pro", "s2-pro", "s1"])
def test_paid_models_blocked_by_default(paid):
    """Default free mode must NEVER send a paid model (fail-closed proof)."""
    with pytest.raises(FishConfigError):
        FishConfig.from_env(_env(FISH_MODEL=paid))


@pytest.mark.parametrize("paid", ["s2.1-pro", "s2-pro", "s1"])
def test_paid_models_require_explicit_opt_in(paid):
    cfg = FishConfig.from_env(_env(FISH_MODEL=paid, ALLOW_PAID_FISH_MODELS="true"))
    assert cfg.model == paid
    assert not cfg.is_free_mode


def test_invalid_latency_rejected():
    with pytest.raises(FishConfigError):
        FishConfig.from_env(_env(FISH_LATENCY="ultrafast"))


def test_invalid_format_rejected():
    with pytest.raises(FishConfigError):
        FishConfig.from_env(_env(FISH_FORMAT="flac"))


def test_numeric_ranges_validated():
    with pytest.raises(FishConfigError):
        FishConfig.from_env(_env(FISH_TEMPERATURE="1.5"))
    with pytest.raises(FishConfigError):
        FishConfig.from_env(_env(FISH_CHUNK_LENGTH="50"))
    with pytest.raises(FishConfigError):
        FishConfig.from_env(_env(FISH_REPETITION_PENALTY="5"))


def test_env_precedence_and_numeric_parsing():
    cfg = FishConfig.from_env(_env(FISH_TEMPERATURE="0.5", FISH_CHUNK_LENGTH="250",
                                   FISH_TTS_TIMEOUT_MS="20000"))
    assert cfg.temperature == 0.5
    assert cfg.chunk_length == 250
    assert cfg.tts_timeout_ms == 20000
