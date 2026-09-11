from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from jarvis.voice.character import CharacterSpec, JARVIS_CHARACTER


@dataclass
class EmotionalState:
    energy: float = 0.5
    happiness: float = 0.5
    seriousness: float = 0.5
    calm: float = 0.5
    excitement: float = 0.5
    playfulness: float = 0.5
    dramatic_intensity: float = 0.5
    surprise: float = 0.2

    def expressiveness(self) -> float:
        return (self.energy + self.excitement + self.playfulness + self.dramatic_intensity) / 4.0


class CharacterEmotionEngine:
    def __init__(self, character: CharacterSpec = JARVIS_CHARACTER) -> None:
        self.character = character
        self.state = EmotionalState(
            energy=character.character_energy,
            playfulness=character.character_playfulness,
            excitement=character.character_expressiveness,
        )

    def reset(self) -> None:
        self.state = EmotionalState(
            energy=self.character.character_energy,
            playfulness=self.character.character_playfulness,
            excitement=self.character.character_expressiveness,
        )

    def update(self, text: str, system_event: Optional[str] = None) -> EmotionalState:
        t = (text or "").lower()
        energy = self.character.character_energy
        happiness = 0.5
        seriousness = 0.5
        calm = 0.5
        excitement = self.character.character_expressiveness
        playfulness = self.character.character_playfulness
        dramatic_intensity = 0.5
        surprise = 0.2

        if system_event == "SUCCESS":
            energy = min(1.0, energy + 0.25)
            happiness = 0.8
            seriousness = 0.3
            excitement = 0.7
        elif system_event == "DELIGHTFUL_SUCCESS":
            energy = min(1.0, energy + 0.35)
            happiness = 0.9
            seriousness = 0.2
            excitement = 0.8
            playfulness = 0.85
        elif system_event == "FAILURE":
            energy = max(0.1, energy - 0.2)
            happiness = 0.2
            seriousness = 0.85
            excitement = 0.2
        elif "critical" in t or "failure" in t or "seconds matters" in t or "going critical" in t:
            energy = 0.9
            dramatic_intensity = 0.95
            seriousness = 0.9
            calm = 0.1
        elif "routine check" in t or "simply" in t:
            energy = 0.4
            dramatic_intensity = 0.2
            calm = 0.85
            seriousness = 0.4
        elif "haha" in t or "hilarious" in t or "wit" in t:
            happiness = 0.85
            playfulness = 0.8
            excitement = 0.75
        elif "anomaly" in t or "unexpected" in t or "what?" in t:
            surprise = 0.9
            dramatic_intensity = 0.75

        self.state = EmotionalState(
            energy=energy,
            happiness=happiness,
            seriousness=seriousness,
            calm=calm,
            excitement=excitement,
            playfulness=playfulness,
            dramatic_intensity=dramatic_intensity,
            surprise=surprise,
        )
        return self.state
