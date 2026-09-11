from __future__ import annotations

import random
import re
from typing import Optional

from jarvis.voice.character import CharacterSpec, JARVIS_CHARACTER
from jarvis.voice.emotion import EmotionalState
from jarvis.voice.prosody import PerformancePlan


class TextPreprocessor:
    def __init__(self, character: CharacterSpec = JARVIS_CHARACTER, seed: int = 42) -> None:
        self.character = character
        self.seed = seed
        self._rng = random.Random(seed)

    def preprocess(self, text: str, state: EmotionalState, profile: PerformancePlan) -> str:
        if not text:
            return ""

        out = text.strip()

        # Remove emojis
        out = re.sub(r"[\U00010000-\U0010ffff]", "", out)

        # Remove markdown symbols and colons
        out = out.replace("**", "").replace("`", "").replace(":", " ")

        # Map known cues
        out = out.replace("[clears throat]", "[clear throat]")

        # Remove unsupported groq cues
        unsupported = ["[heavy sigh]", "[voice trembling]", "[audible fake sob]", "[aggressive sigh]", "[sharp intake of breath]", "[polite throat clear]"]
        for u in unsupported:
            out = out.replace(u, "")

        # Paralinguistic tags
        if "haha" in out.lower() or "hilarious" in out.lower():
            if "[chuckle]" not in out and "[laugh]" not in out:
                if state.happiness > 0.7:
                    out = f"[chuckle] {out}"

        # Ensure no duplicate laugh tags
        if out.count("[laugh]") > 1:
            first = out.find("[laugh]")
            out = out[:first + 7] + out[first + 7:].replace("[laugh]", "")

        # Dramatic ellipsis
        if profile.dramatic_timing > 0.5 and "..." not in out and len(out.split()) > 4:
            if ". " in out:
                out = out.replace(". ", "... ", 1)

        # Reaction prefaces if surprised
        if state.surprise > 0.8:
            prefix = self.character.reactions[self.seed % len(self.character.reactions)]
            if not out.startswith(tuple(self.character.reactions)):
                out = f"{prefix}{out}"

        return " ".join(out.split())
