"""Regression tests for the authoritative personality core (personality.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from personality import (PERSONALITY_BLOCK, build_context_block, estimate_tone,
                         format_for_speech, reset_opener_memory)


def test_tone_frustrated_fail_is_empathetic():
    assert estimate_tone("this took forever!", "fail") == "empathetic"
    assert estimate_tone("open notepad", "fail") == "apologetic"


def test_tone_request_types():
    assert estimate_tone("That's amazing, wow!") == "energetic"
    assert estimate_tone("I need to delete these files urgently") == "serious"
    assert estimate_tone("Open Notepad.") == "focused"
    assert estimate_tone("What's 25 times 18?") == "curious"
    assert estimate_tone("What time is it") == "neutral"


def test_markdown_stripped_facts_kept():
    s, _ = format_for_speech("**Done.** Opened `Notepad`.")
    assert s == "Done. Opened Notepad."
    s, _ = format_for_speech("See [the docs](http://example.com/x) for details.")
    assert "the docs" in s and "http" not in s


def test_sir_discipline():
    reset_opener_memory()
    total = sum(format_for_speech("Certainly! Task complete, sir.", tone="neutral")[0].lower().count("sir")
                for _ in range(6))
    assert total <= 3
    s, _ = format_for_speech("Yes sir, right away sir, done sir.")
    assert s.lower().count("sir") <= 1


def test_opener_variety():
    reset_opener_memory()
    format_for_speech("Done. File saved.")
    s, _ = format_for_speech("Done. Window closed.")
    assert not s.startswith("Done")


def test_length_discipline():
    long_text = " ".join("Sentence number %d with filler content here." % i for i in range(20))
    s, d = format_for_speech(long_text, kind="answer")
    assert len(s.split()) <= 72 and d is not None
    s, _ = format_for_speech("2 plus 2 equals 4.", kind="answer")
    assert s == "2 plus 2 equals 4."


def test_persona_guards():
    assert "do not have feelings" in PERSONALITY_BLOCK
    assert "AT MOST once" in PERSONALITY_BLOCK


def test_context_block():
    ctx = build_context_block([{"role": "user", "content": "open notepad"}],
                              "Notepad is open.", "open notepad")
    assert "Notepad is open" in ctx
