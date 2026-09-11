"""Tests for the S2.1 cue renderer (§10, §20). No API key needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice.cues import (is_sensitive, render_cues, sanitize_user_text,
                        strip_cues_for_display)


def test_neutral_passthrough():
    assert render_cues("Hello there.", "neutral") == "Hello there."
    assert render_cues("Hello there.", "") == "Hello there."


def test_bracket_cue_s21():
    out = render_cues("What a wonderful day!", "happy")
    assert out.startswith("[happy] ")
    assert "What a wonderful day!" in out


def test_unknown_emotion_no_cue():
    assert render_cues("Hi.", "ecstatic-turbo") == "Hi."


def test_sensitive_suppresses_theatrics():
    t = "I am sorry about your loss. The funeral is tomorrow."
    assert render_cues(t, "sad") == t
    assert render_cues("The hospital called with the diagnosis.", "empathetic") == \
        "The hospital called with the diagnosis."
    assert is_sensitive("The backup failed and data loss occurred.")


def test_user_cue_injection_neutralized():
    dirty = "Hello [excited] world (laughing) now"
    clean = sanitize_user_text(dirty)
    assert "[" not in clean and "]" not in clean and "(" not in clean
    assert "excited" in clean and "world" in clean


def test_no_stacking_on_existing_cues():
    assert render_cues("[happy] Already cued.", "sad") == "[happy] Already cued."


def test_s1_syntax_only_when_enabled():
    out = render_cues("Hello.", "happy", model="s1", s1_enabled=True)
    assert out.startswith("(happy)")
    out2 = render_cues("Hello.", "happy", model="s2.1-pro-free", s1_enabled=False)
    assert out2.startswith("[happy]")


def test_never_s1_into_s2_pipeline():
    out = render_cues("Hello.", "happy", model="s2.1-pro-free")
    assert "(" not in out.split("Hello")[0]


def test_max_two_cues_restraint():
    out = render_cues("I understand.", "empathetic", intensity=0.1)
    assert out.count("[") <= 2


def test_display_stays_clean():
    shown = strip_cues_for_display("[happy] What a day!")
    assert shown == "What a day!"
    assert "[" not in shown


def test_facts_preserved():
    t = "The build passes with 435 tests green."
    out = render_cues(t, "excited")
    assert "435 tests green" in out
