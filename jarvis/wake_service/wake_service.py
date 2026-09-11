from __future__ import annotations

import re
import threading
from typing import Callable, Optional

WAKE_WORDS = ["jarvis", "jervis", "jarves", "jarv"]


def _is_wake(text: str) -> bool:
    if not text:
        return False
    # Normalize
    t = text.lower().strip()
    # Check for whole words matching variants
    words = re.findall(r"\b[a-z]+\b", t)
    if not words:
        return False
    # Exact word match
    for w in words:
        if w in ("jarvis", "jervis", "jarves"):
            return True
    # If phrase contains 'wake up' and a wake variant
    if "wake up" in t and any(w in t for w in ("jarvis", "jervis", "jarves")):
        return True
    return False


class WakeService:
    def __init__(self, on_wake_callback: Optional[Callable[[], bool]] = None) -> None:
        self.on_wake_callback = on_wake_callback
        self._running = False
        self._listening = threading.Event()
        self._listening.set()

    @property
    def listening(self) -> bool:
        return self._listening.is_set()

    def _on_wake(self) -> None:
        if self.on_wake_callback:
            success = self.on_wake_callback()
            if success:
                self._listening.clear()
            else:
                self._listening.set()
        else:
            self._listening.clear()

    def start(self) -> None:
        self._running = True
        self._listening.set()

    def stop(self) -> None:
        self._running = False
        self._listening.clear()
