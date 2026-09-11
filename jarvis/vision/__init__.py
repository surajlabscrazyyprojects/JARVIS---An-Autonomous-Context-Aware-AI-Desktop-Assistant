"""
jarvis.vision
=============
JARVIS vision subsystem: structured UI understanding, deterministic UI-tree
automation and Gemma 3 4B visual analysis — behind one contract (spec section
33). Vision answers "WHAT is visible?" and never drives the mouse itself.
"""
from __future__ import annotations

from jarvis.vision.contracts import (
    Bounds,
    CameraObservation,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    ContextType,
    ElementSource,
    ElementType,
    ExecutionStatus,
    ObservationLevel,
    Point,
    ScreenObservation,
    VisionElement,
    classify_confidence,
)

__all__ = [
    "Bounds",
    "CameraObservation",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "ContextType",
    "ElementSource",
    "ElementType",
    "ExecutionStatus",
    "ObservationLevel",
    "Point",
    "ScreenObservation",
    "VisionElement",
    "classify_confidence",
]