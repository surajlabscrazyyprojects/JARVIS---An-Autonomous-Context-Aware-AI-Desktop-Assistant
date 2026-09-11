from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class CharacterSpec:
    character_id: str = "IRON_MAN"
    character_energy: float = 0.6
    character_playfulness: float = 0.5
    character_expressiveness: float = 0.6
    reactions: Tuple[str, ...] = (
        "Good heavens, ",
        "Indeed, ",
        "Right then, ",
        "Fascinating, ",
        "Most intriguing, ",
        "Well now, ",
    )


JARVIS_CHARACTER = CharacterSpec()
