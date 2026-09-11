from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from jarvis.fastcommand.executor import FastCommandResult
from jarvis.fastcommand.ownership import AudioOwnershipManager
from jarvis.fastcommand.parser import (
    ESCALATE, MISSING_PARAM, FastCommand, FastCommandParser,
    SET_VOLUME, SET_BRIGHTNESS, GET_VOLUME, GET_BRIGHTNESS, MUTE, UNMUTE,
)

RESPONSE_TEMPLATES = {
    "volume_set": "Sure. I've set the volume to {value}% as requested.",
    "muted": "Done. System is muted.",
    "unmuted": "Done. Audio restored.",
    "brightness_set": "Brightness adjusted to {value}%.",
    "volume_got": "Current volume is {volume}%.",
    "app_not_found": "I couldn't find that application. Please check the name.",
}

MISSING_PROMPTS = {
    "volume_value": "What volume level would you like? Please say a number between 0 and 100.",
    "brightness_value": "What brightness level would you like? Please say a number.",
    "target": "What would you like me to open?",
    "file_info": "What should I name the file or folder?",
}


@dataclass
class CommandRecord:
    intent: str
    executed: bool
    response: str = ""
    result: Any = None


class FastCommandCore:
    def __init__(
        self,
        ownership: AudioOwnershipManager,
        parser: FastCommandParser,
        executor: Any,
        speaker: Any,
        confidence_threshold: float = 0.3,
    ) -> None:
        self.ownership = ownership
        self.parser = parser
        self.executor = executor
        self.speaker = speaker
        self.confidence_threshold = confidence_threshold

    def handle_utterance(self, text: str, confidence: float = 1.0) -> Optional[CommandRecord]:
        if not self.ownership.can_listen:
            return None
        if confidence < self.confidence_threshold:
            return None

        cmd: Optional[FastCommand] = self.parser.parse(text)
        if cmd is None:
            return None

        if cmd.intent == ESCALATE:
            msg = "That sounds like a complex request. Say Jarvis followed by your goal for the full assistant."
            self.speaker.speak(msg)
            return CommandRecord(intent=ESCALATE, executed=False, response=msg)

        if cmd.intent == MISSING_PARAM:
            missing = cmd.missing or "target"
            msg = MISSING_PROMPTS.get(missing, "Could you clarify that?")
            self.speaker.speak(msg)
            return CommandRecord(intent=MISSING_PARAM, executed=False, response=msg)

        result = self.executor.execute(cmd)
        response = self._build_response(cmd, result)
        if response:
            self.speaker.speak(response)
        return CommandRecord(intent=cmd.intent, executed=True, response=response, result=result)

    def _build_response(self, cmd: FastCommand, result: FastCommandResult) -> str:
        key = result.response_key if hasattr(result, "response_key") else ""
        tmpl = RESPONSE_TEMPLATES.get(key, "")
        if tmpl:
            return tmpl.format(**{**result.data, "value": cmd.value})
        return ""


class FastResponseSpeaker:
    def __init__(self, tts_url: str = "http://127.0.0.1:8766/tts") -> None:
        self.tts_url = tts_url

    def speak(self, text: str) -> None:
        try:
            import urllib.request
            import json
            data = json.dumps({"text": text}).encode("utf-8")
            req = urllib.request.Request(self.tts_url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1)
        except Exception:
            pass


class FastCommandSTT:
    def __init__(self, model: Any = None) -> None:
        self.model = model

    @property
    def ready(self) -> bool:
        return self.model is not None

    def transcribe(self, audio_bytes: bytes) -> tuple[str, float]:
        if not self.ready:
            return "", 0.0
        return "", 0.0
