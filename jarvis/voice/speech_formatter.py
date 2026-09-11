from __future__ import annotations

import re
from typing import ClassVar, Dict, Optional

from jarvis.voice.emotion_engine import EmotionalMetadata


class SpeechFormatter:
    NONVERBAL_TAGS: ClassVar[Dict[str, str]] = {
        "heavy_sigh": "[heavy sigh]",
        "exasperated_sigh": "[exasperated sigh]",
        "aggressive_sigh": "[aggressive sigh]",
        "sharp_intake": "[sharp intake of breath]",
        "polite_throat_clear": "[polite throat clear]",
        "voice_cracking": "[voice cracking]",
        "voice_trembling": "[voice trembling]",
        "fake_sob": "[audible fake sob]",
        "sniffles": "[sniffles]",
        "maniacal_laughter": "[maniacal laughter]",
        "seething_whisper": "[seething whisper]",
        "dry_chuckle": "[dry chuckle]",
        "chuckle": "[chuckle]",
    }

    EMOTION_PREFIXES: ClassVar[Dict[str, str]] = {
        "exasperated": "[heavy sigh]",
        "maniacal": "[maniacal laughter]",
        "sarcastic": "[dry chuckle]",
        "disgusted": "[aggressive sigh]",
        "dramatic": "[voice trembling]",
        "weeping": "[audible fake sob]",
        "whispering": "[low intense whisper]",
    }

    def format_speech(self, text: str, meta: Optional[EmotionalMetadata] = None) -> str:
        if not text:
            return ""

        formatted = text.strip()

        # Normalize parenthesis tags to square brackets: (excited) -> [excited]
        formatted = re.sub(r"\(([a-zA-Z\s_-]+)\)", r"[\1]", formatted)

        if meta:
            if meta.nonverbal and meta.nonverbal in self.NONVERBAL_TAGS:
                tag = self.NONVERBAL_TAGS[meta.nonverbal]
                if tag not in formatted:
                    formatted = f"{tag} {formatted}"

            if meta.pause_frequency >= 0.4 and "..." not in formatted:
                if ", " in formatted:
                    formatted = formatted.replace(", ", "... ", 1)
                elif ". " in formatted:
                    formatted = formatted.replace(". ", "... ", 1)

            if meta.emotion in self.EMOTION_PREFIXES and not formatted.startswith("["):
                prefix = self.EMOTION_PREFIXES[meta.emotion]
                formatted = f"{prefix} {formatted}"

        return formatted
