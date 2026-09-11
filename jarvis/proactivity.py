from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ProactiveDecision:
    action: str
    reason: str
    confidence: float


class ProactivityEngine:
    def __init__(self, enabled: bool = False, cooldown_seconds: float = 60.0) -> None:
        self.enabled = enabled
        self.cooldown_seconds = cooldown_seconds
        self._last_spoken: Dict[str, float] = {}

    def evaluate(self, event: str, verified: bool = False, user_available: bool = True) -> ProactiveDecision:
        if event == "TASK_COMPLETED" and verified and self.enabled and user_available:
            now = time.time()
            if now - self._last_spoken.get(event, 0.0) >= self.cooldown_seconds:
                self._last_spoken[event] = now
                return ProactiveDecision("SPEAK", "verified task completion", 0.98)
        if event in {"TASK_FAILED", "TASK_BLOCKED"} and self.enabled and user_available:
            return ProactiveDecision("SPEAK", "task requires attention", 0.95)
        return ProactiveDecision("STAY_SILENT", "event is not interruption-worthy", 0.9)
