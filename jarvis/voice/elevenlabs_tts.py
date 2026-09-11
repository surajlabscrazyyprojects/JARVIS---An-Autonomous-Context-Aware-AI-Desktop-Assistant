from __future__ import annotations

import os
from typing import Dict, Optional

BRITISH_MALE_VOICE_REFERENCES: Dict[str, str] = {
    "george": "JBFqnCBsd6RMkjVDRZzb",
    "callum": "N2lVS1w4EtoT3dr4eOWO",
    "charlie": "IKne3meq5aSn9XLyUdCD",
    "paul_bettany": "JBFqnCBsd6RMkjVDRZzb",
}

BRAINROT_CUE_NORMALIZATION_MAP: Dict[str, str] = {
    "heavy sigh": "[heavy sigh]",
    "inhales sharply": "[inhales sharply]",
    "polite throat clear": "[polite throat clear]",
    "voice cracking": "[voice cracking]",
    "voice trembling": "[voice trembling]",
    "audible fake sob": "[audible fake sob]",
    "sniffles": "[sniffles]",
    "starts chuckling softly": "[starts chuckling softly]",
    "laughs uncontrollably": "[laughs uncontrollably]",
    "laughs maniacally": "[laughs maniacally]",
    "catches breath": "[catches breath]",
    "voice drops to a low intense whisper": "[voice drops to a low intense whisper]",
    "laughs nervously": "[laughs nervously]",
    "chuckles dryly": "[chuckles dryly]",
    "slow clap": "[slow clap]",
}


class ElevenLabsTTSClient:
    def __init__(self, api_key: Optional[str] = None, default_voice_id: Optional[str] = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("ELEVENLABS_API_KEY", "")
        env_voice = os.environ.get("BRAINROT_JARVIS_VOICE_ID", "")
        self.default_voice_id = default_voice_id or env_voice or BRITISH_MALE_VOICE_REFERENCES["george"]
        self.model = "eleven_multilingual_v2"
        self.stability = 0.35
        self.style = 0.65
        self.similarity_boost = 0.75

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())
