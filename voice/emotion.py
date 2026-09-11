"""Emotion engine for JARVIS: one shared EmotionState drives both voice
delivery and the character/ring. The TTS layer performs the emotion using only
controls the actual engine supports (kokoro speed + pitch/energy post), so a
NEUTRAL vs EMPATHETIC delivery of the same text sounds meaningfully different.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

# The 18 emotional states from the replacement spec.
EMOTIONS = [
    "neutral", "calm", "happy", "excited", "very_excited", "amused",
    "curious", "surprised", "confident", "supportive", "empathetic",
    "sad", "serious", "tired", "bored", "frustrated", "relieved", "celebratory",
]

# Emotion -> delivery. speed is the kokoro speed multiplier (pace), pitch_cents
# is the pitch shift applied on the SAME speaker identity (energy/intonation),
# energy is a 0..1 character-animation level. Identity never changes.
_DELIVERY: dict[str, tuple[float, int, float]] = {
    "neutral":       (1.00,   0, 0.50),
    "calm":          (0.95, -20, 0.40),
    "happy":         (1.06,  40, 0.65),
    "excited":       (1.14,  70, 0.85),
    "very_excited":  (1.22, 100, 0.95),
    "amused":        (1.06,  45, 0.65),
    "curious":       (1.04,  30, 0.60),
    "surprised":     (1.10,  80, 0.85),
    "confident":     (1.02,  15, 0.75),
    "supportive":    (0.97,  10, 0.60),
    "empathetic":    (0.92, -15, 0.45),
    "sad":           (0.88, -70, 0.30),
    "serious":       (0.94, -30, 0.60),
    "tired":         (0.85, -60, 0.25),
    "bored":         (0.90, -35, 0.30),
    "frustrated":    (1.08,  20, 0.85),
    "relieved":      (0.98,   5, 0.50),
    "celebratory":   (1.18,  90, 0.95),
}

# Alias map for normalization (callers/tests/HUD may use informal names).
_ALIASES = {
    "normal": "neutral", "default": "neutral", "flat": "neutral",
    "energic": "excited", "energetic": "excited", "amped": "excited",
    "pumped": "excited", "hyped": "excited",
    "ecstatic": "very_excited", "hype": "very_excited", "overjoyed": "very_excited",
    "joyful": "happy", "joy": "happy", "cheerful": "happy",
    "funny": "amused", "humorous": "amused", "amuse": "amused", "playful": "amused",
    "shocked": "surprised", "wow": "surprised", "wonder": "surprised", "whoa": "surprised",
    "inquisitive": "curious", "questioning": "curious",
    "assertive": "confident", "confident": "confident",
    "reassuring": "supportive", "helpful": "supportive", "encouraging": "supportive",
    "sympathetic": "empathetic", "empathetic": "empathetic", "kind": "empathetic",
    "unhappy": "sad", "down": "sad", "gloomy": "sad",
    "solemn": "serious", "dramatic": "serious", "firm": "serious",
    "sleepy": "tired", "exhausted": "tired", "weary": "tired",
    "whisper": "calm", "quiet": "calm", "hushed": "calm",
    "frustrated": "frustrated", "annoyed": "frustrated", "angry": "frustrated",
    "irritated": "frustrated", "frustration": "frustrated",
    "relieved": "relieved", "whew": "relieved",
    "celebration": "celebratory", "triumphant": "celebratory", "victorious": "celebratory",
}


def normalize_emotion(name: Optional[str]) -> Optional[str]:
    """Return the canonical emotion id or None if unrecognized."""
    if not name:
        return None
    key = str(name).strip().lower().strip()
    key_sp = key.replace("_", " ").replace("-", " ").strip()
    key_sp = re.sub(r"\s+", " ", key_sp)
    key_us = key_sp.replace(" ", "_")
    if key_sp in _ALIASES:
        return _ALIASES[key_sp]
    if key_us in _ALIASES:
        return _ALIASES[key_us]
    if key_sp in EMOTIONS or key_us in EMOTIONS:
        return key_us if key_us in EMOTIONS else key_sp
    # Substring match, longest first so very_excited beats excited
    for e in sorted(EMOTIONS, key=len, reverse=True):
        e_sp = e.replace("_", " ")
        if e == key_us or e_sp == key_sp or e in key_us or e_sp in key_sp:
            return e
    for alias, canon in _ALIASES.items():
        alias_sp = alias.replace("_", " ")
        if alias == key_us or alias_sp == key_sp or alias in key_us or alias_sp in key_sp:
            return canon
    return None


def delivery_for(emotion: str) -> tuple[float, int, float]:
    canon = normalize_emotion(emotion) or "neutral"
    speed, pitch, energy = _DELIVERY[canon]
    return speed, pitch, energy


@dataclass
class SpeechPerformance:
    emotion: str = "neutral"
    intensity: float = 0.75
    speed: float = 1.0      # kokoro pace multiplier (delivery pace)
    pitch_cents: int = 0    # pitch shift in cents (energy/intonation)
    energy: float = 0.5     # 0..1 for voice + character animation


@dataclass
class CharacterProfile:
    voice_id: str = "am_michael"
    personality: str = "young_adult_conversational"
    accent: str = "american"
    language: str = "en"


# Lexical hints for auto emotion selection (conversational model context).
_CELEBRATORY = re.compile(r"\b(we\s+(did|fixed|got|made)\s+it|victory|hooray|finally|let'?s\s+go|yay|it\s+works!?)\b", re.I)
_EXCITED = re.compile(r"(\!+|awesome|amazing|perfect!|that's\s+great|can't\s+wait|super\s+cool)", re.I)
_AMUSED = re.compile(r"\b(haha|lol|hilarious|funny|that'?s\s+pretty\s+funny|nice\s+try)\b", re.I)
_SAD = re.compile(r"\b(aw|rough|sad|failed|bad\s+news|sorry)\b", re.I)
_SUPPORTIVE = re.compile(r"\b(don'?t\s+worry|you'?ll\s+get\s+it|we'?ll\s+(figure|do)|next time|it'?s\s+okay|i'?ve\s+got\s+you)\b", re.I)
_CURIOUS = re.compile(r"\?")
_SURPRISED = re.compile(r"\b(wait|seriously|really\?|what\?!|no\s+way|whoa|wow)\b", re.I)
_CELEBRATORY_WORD = re.compile(r"\b(celebrat|legendary|incredible\s+job|heck\s+yeah)\b", re.I)


class EmotionDirector:
    """Chooses the emotional delivery for a segment of text."""

    def __init__(self, character: CharacterProfile | None = None):
        self.character = character or CharacterProfile()

    def classify(self, text: str, override: Optional[str] = None,
                 mode: str = "auto", base_intensity: float = 0.75,
                 intensity: Optional[float] = None) -> SpeechPerformance:
        text = (text or "").strip()
        if mode == "manual":
            emotion = normalize_emotion(override) or "neutral"
        else:
            emotion = normalize_emotion(override) or self._lexical(text)
        inten = float(intensity) if intensity is not None else base_intensity
        inten = max(0.0, min(1.0, inten))
        speed, pitch, energy = delivery_for(emotion)
        # Intensity scales the delivery so "just a little excited" stays subtle.
        frac = 0.6 + 0.4 * inten
        speed = 1.0 + (speed - 1.0) * frac
        pitch = int(round(pitch * frac))
        energy = max(0.0, min(1.0, energy * inten))
        return SpeechPerformance(emotion=emotion, intensity=inten,
                                 speed=speed, pitch_cents=pitch, energy=energy)

    @staticmethod
    def _lexical(text: str) -> str:
        if _CELEBRATORY.search(text) or _CELEBRATORY_WORD.search(text):
            return "celebratory"
        if _EXCITED.search(text):
            return "excited"
        if _SURPRISED.search(text):
            return "surprised"
        if _AMUSED.search(text):
            return "amused"
        if _SAD.search(text):
            return "empathetic"
        if _SUPPORTIVE.search(text):
            return "supportive"
        if _CURIOUS.search(text):
            return "curious"
        return "neutral"


@dataclass
class EmotionState:
    """Shared emotional state - the ONE source of truth for voice + character.

    The character/ring consumes exactly the same state as the voice.
    """
    current: str = "neutral"
    profile: str = "neutral"
    previous: str = "neutral"
    intensity: float = 0.75
    energy: float = 0.5
    voice_id: str = "am_michael"
    updated_at: float = field(default_factory=time.time)

    def update_from_performance(self, perf: SpeechPerformance, voice_id: str = "am_michael"):
        self.previous = self.current
        self.current = perf.emotion
        self.profile = self.current
        self.intensity = perf.intensity
        self.energy = perf.energy
        self.voice_id = voice_id
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        return {
            "current": self.current,
            "profile": self.profile,
            "previous": self.previous,
            "intensity": self.intensity,
            "energy": self.energy,
            "voice_id": self.voice_id,
            "updated_at": round(self.updated_at, 3),
        }