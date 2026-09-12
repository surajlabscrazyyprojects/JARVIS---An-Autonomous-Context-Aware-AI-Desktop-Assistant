"""Privacy and operating-mode controls for screen vision.

The controller is intentionally small and process-local.  It is consulted
before a screen capture, OCR pass, or remote vision request.  Raw images are
never retained by this component.
"""
from __future__ import annotations

from enum import Enum
from threading import RLock


class VisionMode(str, Enum):
    OFF = "OFF"
    ON_DEMAND = "ON_DEMAND"
    TASK_AWARE = "TASK_AWARE"
    CONTINUOUS_LOW_RATE = "CONTINUOUS_LOW_RATE"


class VisionPrivacy:
    def __init__(self, enabled: bool = True, mode: VisionMode = VisionMode.ON_DEMAND) -> None:
        self._enabled = bool(enabled)
        self._mode = VisionMode(mode)
        self._remote_allowed = False
        self._lock = RLock()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled and self._mode != VisionMode.OFF

    @property
    def mode(self) -> VisionMode:
        with self._lock:
            return self._mode

    @property
    def remote_allowed(self) -> bool:
        with self._lock:
            return self._remote_allowed

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)
            if not self._enabled:
                self._mode = VisionMode.OFF
            elif self._mode == VisionMode.OFF:
                self._mode = VisionMode.ON_DEMAND

    def set_mode(self, mode: VisionMode | str) -> None:
        with self._lock:
            self._mode = VisionMode(mode)
            self._enabled = self._mode != VisionMode.OFF

    def set_remote_allowed(self, allowed: bool) -> None:
        with self._lock:
            self._remote_allowed = bool(allowed)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "enabled": self._enabled and self._mode != VisionMode.OFF,
                "mode": self._mode.value,
                "remote_allowed": self._remote_allowed,
                "raw_capture_retention": False,
            }


__all__ = ["VisionMode", "VisionPrivacy"]
