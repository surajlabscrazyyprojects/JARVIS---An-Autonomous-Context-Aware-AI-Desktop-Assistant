from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

SUPPORTED_EMOTIONS: List[str] = [
    "calm",
    "excited",
    "focused",
    "confident",
    "curious",
    "urgent",
    "exasperated",
    "maniacal",
    "sarcastic",
    "disgusted",
    "dramatic",
    "roasting",
    "weeping",
    "whispering",
    "celebratory",
    "disappointed",
    "frustrated",
    "affectionate",
    "mysterious",
    "determined",
    "analytical",
    "playful",
    "serious",
    "surprised",
    "reassuring",
    "thoughtful",
    "neutral",
    "ironic",
    "droll",
    "stoic",
    "amused",
    "apologetic",
]

EMOTION_PROSODY_DEFAULTS: Dict[str, Dict[str, float]] = {
    "calm": {"energy": 0.5, "rate": 1.0, "pitch": 0.5, "warmth": 0.6, "pause": 0.3},
    "excited": {"energy": 0.9, "rate": 1.15, "pitch": 0.7, "warmth": 0.7, "pause": 0.2},
    "focused": {"energy": 0.6, "rate": 0.98, "pitch": 0.5, "warmth": 0.4, "pause": 0.3},
    "confident": {"energy": 0.7, "rate": 1.02, "pitch": 0.55, "warmth": 0.6, "pause": 0.25},
    "curious": {"energy": 0.65, "rate": 1.05, "pitch": 0.6, "warmth": 0.55, "pause": 0.3},
    "urgent": {"energy": 0.95, "rate": 1.20, "pitch": 0.75, "warmth": 0.2, "pause": 0.15},
    "exasperated": {"energy": 0.5, "rate": 0.82, "pitch": 0.45, "warmth": 0.2, "pause": 0.5},
    "maniacal": {"energy": 0.95, "rate": 1.25, "pitch": 0.8, "warmth": 0.15, "pause": 0.15},
    "sarcastic": {"energy": 0.65, "rate": 0.95, "pitch": 0.5, "warmth": 0.2, "pause": 0.4},
    "disgusted": {"energy": 0.75, "rate": 0.90, "pitch": 0.4, "warmth": 0.10, "pause": 0.45},
    "dramatic": {"energy": 0.85, "rate": 0.88, "pitch": 0.65, "warmth": 0.3, "pause": 0.55},
    "roasting": {"energy": 0.85, "rate": 1.08, "pitch": 0.55, "warmth": 0.2, "pause": 0.35},
    "weeping": {"energy": 0.4, "rate": 0.80, "pitch": 0.45, "warmth": 0.3, "pause": 0.6},
    "whispering": {"energy": 0.3, "rate": 0.88, "pitch": 0.35, "warmth": 0.35, "pause": 0.5},
}


@dataclass
class EmotionalMetadata:
    emotion: str = "calm"
    intensity: float = 0.5
    speaking_rate: float = 1.0
    warmth: float = 0.5
    energy: float = 0.5
    pitch_shift: float = 0.0
    pause_frequency: float = 0.3
    nonverbal: Optional[str] = None
    nonverbal_tags: List[str] = field(default_factory=list)


class EmotionalStateTracker:
    def __init__(self, momentum: float = 0.65) -> None:
        self.momentum = momentum
        self.current_emotion = "calm"
        self.intensity = 0.5
        self.speaking_rate = 1.0
        self.warmth = 0.5
        self.energy = 0.5

    def transition(self, target: EmotionalMetadata) -> EmotionalMetadata:
        alpha = self.momentum
        self.current_emotion = target.emotion
        self.intensity = (1.0 - alpha) * self.intensity + alpha * target.intensity
        self.speaking_rate = (1.0 - alpha) * self.speaking_rate + alpha * target.speaking_rate
        self.warmth = (1.0 - alpha) * self.warmth + alpha * target.warmth
        self.energy = (1.0 - alpha) * self.energy + alpha * target.energy
        return EmotionalMetadata(
            emotion=self.current_emotion,
            intensity=self.intensity,
            speaking_rate=self.speaking_rate,
            warmth=self.warmth,
            energy=self.energy,
            pitch_shift=target.pitch_shift,
            pause_frequency=target.pause_frequency,
            nonverbal=target.nonverbal,
            nonverbal_tags=target.nonverbal_tags,
        )

    def smooth_update(self, target: EmotionalMetadata) -> EmotionalMetadata:
        return self.transition(target)


class EmotionEngine:
    def __init__(self, character_id: str = "IRON_MAN") -> None:
        self.character_id = character_id
        self.tracker = EmotionalStateTracker(momentum=0.65)

    def analyze_context(self, text: str, system_event: Optional[str] = None) -> EmotionalMetadata:
        t = (text or "").lower()
        emotion = "calm"
        intensity = 0.5
        speaking_rate = 1.0
        warmth = 0.5
        energy = 0.5
        pitch_shift = 0.0
        pause_freq = 0.3
        nonverbal = None
        nonverbal_tags = []

        if system_event == "SUCCESS":
            emotion = "confident"
            intensity = 0.8
            speaking_rate = 1.02
            warmth = 0.6
            energy = 0.65
        elif system_event in ("WARNING", "DANGER"):
            emotion = "disgusted"
            intensity = 0.90
            speaking_rate = 1.05
            warmth = 0.2
            energy = 0.75
        elif system_event == "BRAINROT_ROAST":
            emotion = "roasting"
            intensity = 0.90
        elif system_event == "BRAINROT_MANIACAL_LAUGHTER":
            emotion = "maniacal"
            intensity = 0.98
        elif system_event == "BRAINROT_HEAVY_SIGH":
            emotion = "exasperated"
            intensity = 0.85
        elif system_event == "BRAINROT_WEEPING_CODE_TRAGEDY":
            emotion = "weeping"
            intensity = 0.90
        elif system_event == "BRAINROT_SEETHING_WHISPER":
            emotion = "whispering"
            intensity = 0.80
        elif system_event == "BRAINROT_DISGUST":
            emotion = "disgusted"
            intensity = 0.90
        elif system_event == "BRAINROT_SARCASTIC_SUCCESS":
            emotion = "sarcastic"
            intensity = 0.80
        elif system_event == "BRAINROT_DRAMATIC_BREAKDOWN":
            emotion = "dramatic"
            intensity = 0.90
        elif "heavy sigh" in t or "massive" in t or "energy" in t or ("schedule" in t and "outfit" in t):
            emotion = "exasperated"
            intensity = 0.90
            speaking_rate = 0.90
            warmth = 0.25
            energy = 0.45
            nonverbal = "heavy_sigh"
            nonverbal_tags.append("heavy_sigh")
        elif "weeping" in t or "tragedy" in t or "sobbing" in t or "sniffles" in t or "voice trembling" in t:
            emotion = "weeping"
            intensity = 0.95
            speaking_rate = 0.85
            warmth = 0.3
            energy = 0.35
            nonverbal = "sniffles"
            nonverbal_tags.append("sniffles")
        elif "roblox" in t or "skibidi" in t or "toilet" in t:
            emotion = "disgusted"
            intensity = 0.95
            speaking_rate = 0.92
            warmth = 0.15
            energy = 0.75
            nonverbal = "aggressive_sigh"
            nonverbal_tags.append("aggressive_sigh")
        elif any(w in t for w in ["delulu", "cooked", "maniacal", "chuckling turns into full laughter", "laughing"]):
            emotion = "maniacal"
            intensity = 0.98
            speaking_rate = 1.25
            warmth = 0.2
            energy = 0.98
            nonverbal = "maniacal_laughter"
            nonverbal_tags.append("maniacal_laughter")
        elif "wait" in t or "unexpected" in t or "found" in t:
            emotion = "curious"
            intensity = 0.70
            speaking_rate = 1.02
            warmth = 0.5
            energy = 0.6
        elif any(w in t for w in ["whisper", "quietly", "secret"]):
            emotion = "whispering"
            intensity = 0.75
            speaking_rate = 0.85
            warmth = 0.35
            energy = 0.3
        elif any(w in t for w in ["roast", "giving massive", "zero rizz"]):
            emotion = "roasting"
            intensity = 0.90
            speaking_rate = 1.08
            warmth = 0.2
            energy = 0.75

        meta = EmotionalMetadata(
            emotion=emotion,
            intensity=intensity,
            speaking_rate=speaking_rate,
            warmth=warmth,
            energy=energy,
            pitch_shift=pitch_shift,
            pause_frequency=pause_freq,
            nonverbal=nonverbal,
            nonverbal_tags=nonverbal_tags,
        )
        return self.tracker.transition(meta)
