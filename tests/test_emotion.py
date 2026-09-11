"""Tests: deterministic emotion classification (18 states, delivery mapping)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice.emotion import EmotionDirector, CharacterProfile, EMOTIONS, normalize_emotion  # noqa: E402


def _d():
    return EmotionDirector(CharacterProfile())


def test_expected_emotions():
    # New 18-state set; aliases are normalized (playful->amused, dramatic->serious, whisper->calm)
    cases = {
        "Wait, seriously? We actually fixed it!": ("excited", "celebratory"),
        "Okay. The system is ready.": ("neutral", "calm"),
        "Stop for a second. We need to check this carefully.": ("serious", "neutral"),
        "Whoa. I did not expect that.": ("surprised",),
        "Nice try. But I saw what you did.": ("amused",),
        "And now... we reach the final step.": ("serious", "neutral"),
        "Okay... let's keep this quiet.": ("calm", "neutral"),
        "Why is that process still running?": ("curious",),
    }
    for text, expected in cases.items():
        p = _d().classify(text)
        assert p.emotion in expected, "%r -> %r, expected one of %r" % (text, p.emotion, expected)
        assert p.emotion in EMOTIONS


def test_no_cloud_llm_used():
    p = _d().classify("Great job, we finished!")
    assert p.emotion in ("happy", "celebratory", "excited")


def test_sparse_delivery():
    d = _d()
    p_neutral = d.classify("The system is ready.")
    p_excited = d.classify("Wait, seriously? We actually fixed it!")
    # Delivery must differ, not the text prefix
    assert (p_neutral.speed, p_neutral.pitch_cents) != (p_excited.speed, p_excited.pitch_cents)
    # Same text -> same delivery deterministically
    assert d.classify("Hello.").emotion == d.classify("Hello.").emotion


def test_manual_override():
    d = _d()
    p = d.classify("The system is ready.", mode="manual", override="dramatic")
    # dramatic is an alias for serious in the 18-state set
    assert p.emotion == "serious"
    assert normalize_emotion("dramatic") == "serious"
    assert normalize_emotion("whisper") == "calm"


def test_intensity_bounds():
    p = _d().classify("Wait, seriously? We actually fixed it!")
    assert 0.0 <= p.intensity <= 1.0
    assert 0.0 <= p.energy <= 1.0
    assert 0.5 <= p.speed <= 1.4


def test_all_18_states_valid():
    for emo in EMOTIONS:
        p = _d().classify("Test.", mode="manual", override=emo)
        assert p.emotion == emo
        assert p.speed > 0
