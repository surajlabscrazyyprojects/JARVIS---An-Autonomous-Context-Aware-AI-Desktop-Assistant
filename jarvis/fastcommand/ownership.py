from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Optional


class AudioOwnershipMode(str, Enum):
    FAST_COMMAND = "FAST_COMMAND_MODE"
    JARVIS = "JARVIS_MODE"
    DISABLED = "DISABLED"


class AudioOwnershipManager:
    def __init__(self, state_file: Optional[Path] = None, owner: str = "system") -> None:
        self._mode = AudioOwnershipMode.FAST_COMMAND
        self._state_file = Path(state_file) if state_file else None
        self._owner = owner

    @property
    def mode(self) -> AudioOwnershipMode:
        return self._mode

    @property
    def can_listen(self) -> bool:
        return self._mode == AudioOwnershipMode.FAST_COMMAND

    @property
    def can_speak(self) -> bool:
        return self._mode == AudioOwnershipMode.FAST_COMMAND

    def enter_jarvis(self) -> bool:
        if self._mode == AudioOwnershipMode.DISABLED:
            return False
        self._mode = AudioOwnershipMode.JARVIS
        self._persist()
        return True

    def release(self) -> None:
        self._mode = AudioOwnershipMode.FAST_COMMAND
        self._persist()

    def disable(self) -> None:
        self._mode = AudioOwnershipMode.DISABLED
        self._persist()

    def transition_to(self, mode: AudioOwnershipMode) -> None:
        self._mode = mode
        self._persist()

    def _persist(self) -> None:
        if self._state_file:
            self._state_file.write_text(
                json.dumps({"mode": self._mode.value, "owner": self._owner}),
                encoding="utf-8",
            )
