from __future__ import annotations

from enum import Enum
from typing import Any, Callable, List, Optional


class VoiceState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"


class VoiceStateMachine:
    def __init__(self) -> None:
        self._state: VoiceState = VoiceState.IDLE
        self._listeners: List[Callable[[VoiceState, VoiceState, Any], None]] = []

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def is_speaking(self) -> bool:
        return self._state == VoiceState.SPEAKING

    @property
    def is_interrupted(self) -> bool:
        return self._state == VoiceState.INTERRUPTED

    def on_state_change(self, callback: Callable[[VoiceState, VoiceState, Any], None]) -> None:
        self._listeners.append(callback)

    def transition_to(self, new_state: VoiceState, meta: Any = None) -> None:
        old_state = self._state
        self._state = new_state
        for cb in self._listeners:
            try:
                cb(old_state, new_state, meta)
            except Exception:
                pass

    def interrupt(self, reason: str = "user_barge_in") -> bool:
        if self._state == VoiceState.SPEAKING:
            self.transition_to(VoiceState.INTERRUPTED, {"reason": reason})
            return True
        return False
