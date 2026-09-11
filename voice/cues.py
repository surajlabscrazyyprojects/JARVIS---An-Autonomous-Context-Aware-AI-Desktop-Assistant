"""Model-aware Fish Audio cue renderer (§10 of the voice spec).

Authoritative source: https://docs.fish.audio/developer-guide/core-features/emotions
  * S2 / S2.1 (incl. s2.1-pro-free): ``[bracket]`` free-form cues, placed at the
    sentence start. Max ~3 combined; we use at most 2, usually 1.
  * S1 legacy: ``(parentheses)`` fixed set — only emitted when S1 is explicitly
    enabled, never into an S2/S2.1 pipeline.

Safety rules enforced + tested in tests/test_fish_cues.py:
  * Sensitive content (tragic/medical/legal/safety/distress) suppresses ALL
    theatrical cues — neutral delivery only.
  * User-provided ``[bracket]``/``(paren)`` text is escaped so user input can
    never inject voice controls.
  * Visible text stays clean: cues live only in the TTS-bound string.
  * No pitch parameter is invented (Fish documents speed + volume only).
"""
from __future__ import annotations

import re

# Internal planner emotions -> official S2.1 cue words (docs "Complete Emotion
# Reference"). Only cues from the official tables are emitted.
_EMOTION_CUE = {
    "happy": "happy", "excited": "excited", "very_excited": "excited",
    "amused": "amused", "curious": "curious", "surprised": "surprised",
    "confident": "confident", "supportive": "supportive",
    "empathetic": "empathetic", "sad": "sad", "serious": "serious",
    "tired": "tired", "bored": "bored", "frustrated": "frustrated",
    "relieved": "relieved", "celebratory": "excited", "calm": "calm",
    "neutral": "",
}

# Delivery modifiers (docs "Sound & Delivery Markers") by internal emotion.
_DELIVERY_CUE = {
    "empathetic": "softly",
    "sad": "softly",
    "serious": "calmly",
    "calm": "calmly",
    "excited": None,
    "very_excited": None,
    "celebratory": None,
    "neutral": None,
}

# Content where theatrical delivery is forbidden (spec: never perform grief,
# vulnerability, medical, legal, safety or distress content).
_SENSITIVE_RE = re.compile(
    r"\b(died|death|dead|funeral|grief|cancer|hospital|emergency|diagnos|"
    r"suicid|self-?harm|abuse|assault|lawsuit|court|arrest|police|"
    r"critical\s+failure|data\s+loss|backup\s+failed)\b", re.I)

# User text that looks like a cue — must be neutralized before rendering.
_CUE_LIKE_RE = re.compile(r"[\[\(][^\[\]\(\)]{1,40}[\]\)]")

# Intensity words (docs "Intensity Modifiers").
_INTENSITY_WORD = {0: "slightly", 1: "", 2: "very"}


def _intensity_bucket(intensity: float) -> int:
    try:
        v = max(0.0, min(1.0, float(intensity)))
    except (TypeError, ValueError):
        v = 0.75
    if v < 0.35:
        return 0
    if v > 0.85:
        return 2
    return 1


def sanitize_user_text(text: str) -> str:
    """Escape cue-like spans in USER input so they cannot drive the voice."""
    def _esc(m: re.Match) -> str:
        inner = m.group(0)
        # Keep the words, drop the control characters.
        return inner.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    return _CUE_LIKE_RE.sub(_esc, text or "")


def is_sensitive(text: str) -> bool:
    return bool(_SENSITIVE_RE.search(text or ""))


def render_cues(text: str, emotion: str = "neutral", intensity: float = 0.75,
                model: str = "s2.1-pro-free", s1_enabled: bool = False) -> str:
    """Render TTS-bound text with model-correct emotion cues.

    Returns ``text`` unchanged when neutral / sensitive / unknown model.
    Never invents parameters; never alters factual content.
    """
    t = (text or "").strip()
    if not t:
        return ""
    emo = (emotion or "neutral").strip().lower()
    if emo in ("neutral", "normal", "flat", ""):
        return t
    if is_sensitive(t):
        return t  # neutral delivery only — no theatrics, ever
    if s1_enabled and ("s1" in (model or "").lower()):
        return _render_s1(t, emo, intensity)
    cue = _EMOTION_CUE.get(emo)
    if cue is None:
        return t  # unknown emotion -> no cue rather than a wrong one
    bucket = _intensity_bucket(intensity)
    mod = _INTENSITY_WORD[bucket]
    head = f"[{mod} {cue}]" if mod else f"[{cue}]"
    delivery = _DELIVERY_CUE.get(emo)
    # At most 2 cues; delivery cue only when it adds restraint (soft/calm).
    if delivery and bucket == 0:
        head = f"[{delivery}] {head}"
    if t.startswith("["):
        return t  # never stack onto/nest existing cues
    return f"{head} {t}"


def _render_s1(text: str, emotion: str, intensity: float) -> str:
    """S1 legacy path — parentheses, fixed set. Only when S1 explicitly on."""
    cue = _EMOTION_CUE.get(emotion, "")
    if not cue:
        return text
    bucket = _intensity_bucket(intensity)
    mod = _INTENSITY_WORD[bucket]
    head = f"({mod} {cue})" if mod else f"({cue})"
    if text.startswith("("):
        return text
    return f"{head} {text}"


def strip_cues_for_display(tts_text: str) -> str:
    """Remove rendered cues for UI display / logs (visible text stays clean)."""
    return _CUE_LIKE_RE.sub("", tts_text or "").strip()
