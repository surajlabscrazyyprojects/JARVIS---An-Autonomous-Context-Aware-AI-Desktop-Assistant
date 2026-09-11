"""
jarvis.vision.visual_memory
===========================
Ephemeral, short-lived visual state (spec section 24) plus stale-target
protection (section 25).

We deliberately retain NO screenshots. Only compact fingerprints (hashes),
titles and element metadata are kept. Any meaningful UI transition invalidates
previous coordinates so the motor layer never blindly clicks a stale target.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from jarvis.vision.contracts import Bounds, ScreenObservation, VisionElement

# A target older than this (seconds) is considered stale even if the screen
# has not visibly changed (dialog timers, animations, focus shifts).
TARGET_MAX_AGE = 15.0


class VisualMemory:
    def __init__(self) -> None:
        self.screen_hash: str = ""
        self.application: str = ""
        self.window_title: str = ""
        self.window_bounds: Bounds = Bounds()
        self.elements: List[VisionElement] = []
        self._elements_ts: float = 0.0
        self.target_element: Optional[VisionElement] = None
        self.target_acquired_ts: float = 0.0
        self.last_action: str = ""
        self.last_action_ts: float = 0.0
        self._invalidate_reason: str = ""

    # -- recording ----------------------------------------------------------
    def record(self, obs: ScreenObservation) -> None:
        """Store an observation in the short-lived visual memory."""
        self.screen_hash = obs.screen_hash
        self.application = obs.application
        self.window_title = obs.window_title
        self.window_bounds = obs.window_bounds
        if obs.elements:
            self.elements = obs.elements
            self._elements_ts = obs.timestamp
        # A UI transition invalidates any previously acquired target.
        if self._transitioned(obs):
            self.invalidate_target(reason="screen transition during observation")

    def remember_action(self, action: str) -> None:
        self.last_action = action
        self.last_action_ts = time.time()

    # -- assistance checks ---------------------------------------------------
    def _transitioned(self, obs: ScreenObservation) -> bool:
        """True when the new observation differs from what caused the current
        target to be acquired (window/title/hash change)."""
        if not self.screen_hash or not self.target_element:
            return False
        if obs.window_title != self.window_title:
            return True
        if obs.screen_hash and self.screen_hash and obs.screen_hash != self.screen_hash:
            return True
        return False

    # -- stale-target protection ---------------------------------------------
    def invalidate_target(self, reason: str = "") -> None:
        if self.target_element is not None:
            self._invalidate_reason = reason or "invalidate_target()"
        self.target_element = None
        self.target_acquired_ts = 0.0

    def acquire_target(self, element: VisionElement) -> None:
        """Mark an element as the active click/motor target."""
        self.target_element = element
        self.target_acquired_ts = time.time()

    @property
    def target_is_stale(self) -> bool:
        if self.target_element is None:
            return True
        if time.time() - self.target_acquired_ts > TARGET_MAX_AGE:
            return True
        return False

    @property
    def invalidate_reason(self) -> str:
        return self._invalidate_reason

    # -- querying ------------------------------------------------------------
    def find(self, label: str = "", elem_type: str = "", elem_id: str = "") -> Optional[VisionElement]:
        label = (label or "").strip().lower()
        for e in self.elements:
            if elem_id and e.id == elem_id:
                return e
            if label and label in (e.label or "").lower():
                return e
            if elem_type and str(getattr(e.type, "value", e.type)).upper() == elem_type.upper():
                return e
        return None

    def snapshot(self) -> Dict[str, Any]:
        return {
            "screen_hash": self.screen_hash,
            "application": self.application,
            "window_title": self.window_title,
            "element_count": len(self.elements),
            "elements_ts": self._elements_ts,
            "target_element": self.target_element.to_dict() if self.target_element else None,
            "target_ts": self.target_acquired_ts,
            "last_action": self.last_action,
            "last_action_ts": self.last_action_ts,
            "invalidate_reason": self._invalidate_reason,
        }


__all__ = ["TARGET_MAX_AGE", "VisualMemory"]