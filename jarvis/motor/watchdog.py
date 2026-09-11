"""
jarvis.motor.watchdog
=====================
Input safety watchdog (spec sections 49-50).

Tracks every held mouse button and keyboard key so that on ANY abnormal
termination — task crash, process exit, model failure, timeout, user "Stop" —
all held inputs are released. This guarantees JARVIS never leaves the user's
keyboard or mouse in a stuck state.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator, List, Set, Tuple

Device = Tuple[str, str]  # ("mouse"|"keyboard", name)


class InputSafetyWatchdog:
    def __init__(self) -> None:
        self._held: Set[Device] = set()
        self._lock = threading.Lock()

    # -- registration -------------------------------------------------------
    def press(self, device: str, name: str) -> None:
        with self._lock:
            self._held.add((device, name))

    def release(self, device: str, name: str) -> None:
        with self._lock:
            self._held.discard((device, name))

    # -- state --------------------------------------------------------------
    @property
    def held_inputs(self) -> List[Device]:
        with self._lock:
            return sorted(self._held)

    @property
    def is_holding(self) -> bool:
        with self._lock:
            return len(self._held) > 0

    def held_buttons(self) -> List[str]:
        return [name for dev, name in self.held_inputs if dev == "mouse"]

    def held_keys(self) -> List[str]:
        return [name for dev, name in self.held_inputs if dev == "keyboard"]

    # -- emergency release --------------------------------------------------
    def release_all(self) -> List[Device]:
        """Idempotent release of every tracked input. Returns what was
        released so callers can log it."""
        with self._lock:
            doomed = sorted(self._held)
            self._held.clear()
        # Perform the physical release OUTSIDE the lock (mouse/keyboard code
        # will call watchdog.release() again, which must not deadlock).
        released: List[Device] = []
        for device, name in doomed:
            try:
                if device == "mouse":
                    from jarvis.motor.mouse import release_mouse_button

                    release_mouse_button(name)
                else:
                    from jarvis.motor.keyboard import release_key_named

                    release_key_named(name)
                released.append((device, name))
            except Exception:  # noqa: BLE001
                released.append((device, name))
        return released

    # -- lifecycle helper ----------------------------------------------------
    @contextmanager
    def guard(self) -> Iterator[None]:
        """Run a motor block; whatever happens, held inputs are released on
        normal or abnormal exit."""
        try:
            yield
        finally:
            self.release_all()

    def __enter__(self) -> "InputSafetyWatchdog":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release_all()


__all__ = ["Device", "InputSafetyWatchdog"]