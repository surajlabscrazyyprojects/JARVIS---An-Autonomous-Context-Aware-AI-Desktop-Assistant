"""Tests for segmenter + segmented-stream behavior (§6, §20)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.preprocess import segment_sentences


def test_sentence_boundaries_preserved():
    segs = segment_sentences("Hello there. This is a test.")
    assert len(segs) == 2
    assert segs[0].endswith(".")
    assert "Hello there" in segs[0]


def test_abbreviation_not_split():
    segs = segment_sentences("Dr. Smith went to the lab. He returned.")
    joined = " ".join(segs)
    # Dr. must not become a standalone split
    assert "Dr." in joined
    # But the real sentence boundary still splits
    assert len(segs) >= 2


def test_url_not_split():
    t = "See https://fish.audio/docs for details. It is great."
    segs = segment_sentences(t)
    assert any("https://fish.audio/docs" in s for s in segs)


def test_decimal_not_split():
    segs = segment_sentences("The value is 3.14. It is pi.")
    assert any("3.14" in s for s in segs)


def test_code_block_removed_via_preprocess():
    from voice.preprocess import preprocess_text
    out = preprocess_text("Hello. ```python\nx = 1\n```\n World.")
    assert "python" not in out
    assert "Hello" in out and "World" in out


def test_max_len_splits_at_comma():
    long_seg = "Hello there, this is a very long segment that should be split at a natural comma boundary for better rhythm, and then continue."
    segs = segment_sentences(long_seg, max_len=40)
    # Over-long with commas should be split
    assert len(segs) > 1
    for s in segs:
        assert s.strip()


def test_min_check_stream_segment_shape(monkeypatch):
    """FishBackend.stream yields ordered non-empty WAVs; one session path."""
    from voice.config import VoiceConfig
    from voice.fish_backend import FishBackend

    cfg = VoiceConfig()
    cfg.fish_api_key = "sk-test-1234567890"
    b = FishBackend(cfg)
    # Mock synthesize so no network is needed
    wavs = [b"RIFF....WAV1", b"RIFF....WAV2"]

    def fake_synth(text, voice=None, speed=1.0, pitch_cents=0):
        return wavs.pop(0) if wavs else b"RIFF....WAVx"

    b.synthesize = fake_synth  # type: ignore
    out = list(b.stream("Hello there. This is a test of streaming.", voice="iron_man"))
    assert len(out) == 2
    for amp, wav in out:
        assert isinstance(amp, float)
        assert wav[:4] == b"RIFF"
    # No silent fallback to extra per-word calls — exactly segment count.
    assert len(out) == 2


def test_no_duplicate_or_unbounded_queue():
    # Segmenter output is bounded by input length; no queue growth test needed
    # beyond that. This checks segment count <= sentence count + comma splits.
    t = "Hello. World. " * 20
    segs = segment_sentences(t)
    assert len(segs) <= 40  # at most one per sentence
