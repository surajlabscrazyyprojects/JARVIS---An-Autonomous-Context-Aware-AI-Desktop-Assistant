"""Tests: text preprocessing + safe sentence segmentation."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice.preprocess import preprocess_text, segment_sentences  # noqa: E402


def test_strips_markdown_code_urls():
    t = "See `ls -la` and https://example.com/x and ```print(1)``` and **bold** 😊"
    out = preprocess_text(t)
    assert "ls -la" in out
    assert "https://" not in out
    assert "print(1)" not in out
    assert "**bold**" not in out
    assert "😊" not in out  # emoji removed


def test_no_json_or_stacktrace():
    t = '{"key": "value"} and Traceback (most recent call last): File "x.py", line 3'
    out = preprocess_text(t)
    assert "Traceback" not in out
    assert '"key"' not in out


def test_segment_protects_decimals_and_abbrevs():
    t = "Version 3.14 is stable. Mr. Smith said ok. File report.pdf is ready."
    segs = segment_sentences(t)
    joined = " ".join(segs)
    assert "3.14" in joined
    assert "Mr. Smith" in joined
    assert "report.pdf" in joined
    # No empty segments
    assert all(s.strip() for s in segs)


def test_segment_splits_on_boundaries():
    t = "First sentence. Second one! Third?"
    segs = segment_sentences(t)
    assert len(segs) >= 3


def test_empty_text():
    assert preprocess_text("") == ""
    assert segment_sentences("") == []
