"""Single ownership gate for physical desktop input."""
from __future__ import annotations

from contextlib import contextmanager
from threading import RLock
from typing import Iterator


class CursorControlManager:
    """Serializes mouse/keyboard action sequences across concurrent tasks."""
    def __init__(self) -> None:
        self._lock = RLock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._lock:
            yield

CURSOR_CONTROL = CursorControlManager()

__all__ = ["CURSOR_CONTROL", "CursorControlManager"]
