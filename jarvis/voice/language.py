"""Turn-level multilingual language policy and script detection.

This is intentionally conservative: script can be detected locally, while
fine-grained language/dialect claims come from the STT provider.  Bhojpuri is
never silently relabelled as Hindi when the provider cannot distinguish it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LanguageSignal:
    primary: str = "auto"
    confidence: float = 0.0
    script: str = "Latin"
    direction: str = "ltr"
    secondary: str = ""
    code_switch: bool = False
    dialect: str = ""

    def to_dict(self) -> dict:
        return {
            "primary_language": self.primary,
            "confidence": round(float(self.confidence), 3),
            "script": self.script,
            "direction": self.direction,
            "secondary_language": self.secondary,
            "code_switch": self.code_switch,
            "dialect": self.dialect,
        }


_SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F),
    "Bengali": (0x0980, 0x09FF),
    "Gurmukhi": (0x0A00, 0x0A7F),
    "Gujarati": (0x0A80, 0x0AFF),
    "Tamil": (0x0B80, 0x0BFF),
    "Telugu": (0x0C00, 0x0C7F),
    "Kannada": (0x0C80, 0x0CFF),
    "Malayalam": (0x0D00, 0x0D7F),
    "Arabic": (0x0600, 0x06FF),
    "Hebrew": (0x0590, 0x05FF),
}
_SCRIPT_LANGUAGE = {"Devanagari": "hi", "Arabic": "ar", "Hebrew": "he", "Bengali": "bn",
                    "Gurmukhi": "pa", "Gujarati": "gu", "Tamil": "ta", "Telugu": "te",
                    "Kannada": "kn", "Malayalam": "ml"}


def detect_script(text: str) -> tuple[str, str]:
    counts = {name: 0 for name in _SCRIPT_RANGES}
    latin = 0
    for char in text or "":
        cp = ord(char)
        matched = False
        for name, (lo, hi) in _SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                counts[name] += 1
                matched = True
                break
        if not matched and ("LATIN" in unicodedata.name(char, "") or char.isascii() and char.isalpha()):
            latin += 1
    script, count = max(counts.items(), key=lambda item: item[1]) if counts else ("Latin", 0)
    # Preserve a real non-Latin script in mixed speech instead of letting
    # longer Latin product names ("Blender", "Chrome") hide Devanagari.
    if count == 0:
        return "Latin", "ltr"
    return script, "rtl" if script in {"Arabic", "Hebrew"} else "ltr"


def signal_for_text(text: str, language: str = "auto", confidence: float = 0.0) -> LanguageSignal:
    script, direction = detect_script(text)
    latin = bool(re.search(r"[A-Za-z]", text or ""))
    non_latin = script != "Latin"
    code_switch = latin and non_latin
    script_language = _SCRIPT_LANGUAGE.get(script, "")
    secondary = ("en" if non_latin and language not in {"en", "auto"} else script_language) if code_switch else ""
    return LanguageSignal(primary=language or "auto", confidence=float(confidence or 0.0),
                          script=script, direction=direction, secondary=secondary,
                          code_switch=code_switch)


class LanguagePolicy:
    """Keeps turn language separate from temporary/session preference."""
    def __init__(self) -> None:
        self.current_turn = LanguageSignal()
        self.conversation_language = "auto"
        self.preferred_language = "auto"

    def explicit_language(self, text: str) -> Optional[str]:
        t = (text or "").lower()
        if re.search(r"(?:speak|respond|switch|talk).*(?:english|angrezi)|अंग्रेजी में|इंग्लिश में", t):
            return "en"
        if re.search(r"(?:speak|respond|switch|talk).*(?:hindi|हिंदी)|हिंदी में", t):
            return "hi"
        if re.search(r"(?:speak|respond|switch|talk).*(?:bhojpuri|भोजपुरी)|भोजपुरी में", t):
            return "bho"
        return None

    def observe(self, text: str, language: str = "auto", confidence: float = 0.0) -> LanguageSignal:
        explicit = self.explicit_language(text)
        chosen = explicit or language or "auto"
        self.current_turn = signal_for_text(text, chosen, confidence)
        if chosen not in {"auto", ""}:
            self.conversation_language = chosen
        return self.current_turn

    def snapshot(self) -> dict:
        return {
            "current_turn": self.current_turn.to_dict(),
            "conversation_language": self.conversation_language,
            "preferred_language": self.preferred_language,
        }


__all__ = ["LanguagePolicy", "LanguageSignal", "detect_script", "signal_for_text"]
