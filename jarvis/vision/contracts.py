"""
jarvis.vision.contracts
=======================
Structured data contracts for the JARVIS vision layer.

The vision layer answers "WHAT is visible?" in a machine-usable form.
No free-form descriptions are ever returned to the motor/control layer.

These contracts mirror the documented schema (application, window_title,
screen_summary, elements with bounds/center/confidence/type) and add the
metadata the control + verification layers need: execution status,
observation level, screen-change hash and source of truth (uia/vision/win32).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional


class ExecutionStatus(str, Enum):
    """Lifecycle of a vision/motor request (spec: REQUESTED/EXECUTING/
    OBSERVED/VERIFIED/FAILED/CANCELLED). Never mark VERIFIED until the
    expected state is actually observed."""

    REQUESTED = "REQUESTED"
    EXECUTING = "EXECUTING"
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ObservationLevel(IntEnum):
    """Adaptive vision escalation levels (spec section 6)."""

    NONE = 0  # no vision required                    -> L0
    WINDOW_META = 1  # window/application metadata    -> L1
    UI_TREE = 2  # accessibility / UI tree            -> L2
    REGION = 3  # targeted screenshot region          -> L3
    FULL_SCREEN = 4  # full-screen visual analysis    -> L4


class ContextType(str, Enum):
    """Separate observation sources. Screen and camera are NEVER mixed."""

    SCREEN = "screen"
    CAMERA = "camera"


class ElementType(str, Enum):
    BUTTON = "BUTTON"
    ICON = "ICON"
    TEXT_FIELD = "TEXT_FIELD"
    CHECKBOX = "CHECKBOX"
    RADIO = "RADIO"
    DROPDOWN = "DROPDOWN"
    MENU = "MENU"
    TAB = "TAB"
    SLIDER = "SLIDER"
    SCROLLBAR = "SCROLLBAR"
    LIST = "LIST"
    TABLE = "TABLE"
    IMAGE = "IMAGE"
    CANVAS = "CANVAS"
    DIALOG = "DIALOG"
    WINDOW = "WINDOW"
    TOOLBAR = "TOOLBAR"
    PANEL = "PANEL"
    OBJECT = "OBJECT"
    CURSOR_TARGET = "CURSOR_TARGET"


class ElementSource(str, Enum):
    """Where an element came from: deterministic adapters are preferred."""

    UIA = "uia"  # accessibility / UI tree (deterministic)
    WIN32 = "win32"  # window metadata (deterministic)
    VISION = "vision"  # Gemma visual analysis
    OCR = "ocr"
    SYNTHETIC = "synthetic"
@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0

    def to_tuple(self) -> tuple:
        return (int(self.x), int(self.y))

    def __iter__(self):
        yield int(self.x)
        yield int(self.y)


@dataclass
class Bounds:
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2.0, self.y + self.height / 2.0)

    def to_region(self) -> tuple:
        return (int(self.x), int(self.y), int(self.width), int(self.height))

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.right and self.y <= py <= self.bottom


@dataclass
class VisionElement:
    """A single identified UI/visual element (spec section 7/8)."""

    id: str
    type: ElementType | str = ElementType.OBJECT
    label: str = ""
    center: Point = field(default_factory=Point)
    bounds: Bounds = field(default_factory=Bounds)
    interactive: bool = False
    enabled: bool = True
    confidence: float = 0.0
    source: ElementSource | str = ElementSource.VISION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, ElementType) else str(self.type),
            "label": self.label,
            "center": {"x": int(self.center.x), "y": int(self.center.y)},
            "bounds": {
                "x": int(self.bounds.x),
                "y": int(self.bounds.y),
                "width": int(self.bounds.width),
                "height": int(self.bounds.height),
            },
            "interactive": self.interactive,
            "enabled": self.enabled,
            "confidence": round(float(self.confidence), 4),
            "source": self.source.value if isinstance(self.source, ElementSource) else str(self.source),
        }
@dataclass
class ScreenObservation:
    """Structured understanding of the current screen (spec section 4)."""

    context: ContextType = ContextType.SCREEN
    status: ExecutionStatus = ExecutionStatus.OBSERVED
    application: str = ""
    window_title: str = ""
    window_bounds: Bounds = field(default_factory=Bounds)
    screen_size: tuple = (0, 0)
    screen_hash: str = ""
    summary: str = ""
    elements: List[VisionElement] = field(default_factory=list)
    observation_level: ObservationLevel = ObservationLevel.NONE
    cursor: Point = field(default_factory=Point)
    timestamp: float = field(default_factory=time.time)
    degraded: bool = False  # Gemma unavailable / vision degraded
    reused: bool = False  # observation served from screen-change cache
    capture_ms: int = 0
    inference_ms: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context": self.context.value,
            "status": self.status.value,
            "application": self.application,
            "window_title": self.window_title,
            "window_bounds": {
                "x": int(self.window_bounds.x),
                "y": int(self.window_bounds.y),
                "width": int(self.window_bounds.width),
                "height": int(self.window_bounds.height),
            },
            "screen_size": list(self.screen_size),
            "screen_hash": self.screen_hash,
            "summary": self.summary,
            "elements": [e.to_dict() for e in self.elements],
            "observation_level": int(self.observation_level),
            "cursor": {"x": int(self.cursor.x), "y": int(self.cursor.y)},
            "timestamp": self.timestamp,
            "degraded": self.degraded,
            "reused": self.reused,
            "capture_ms": self.capture_ms,
            "inference_ms": self.inference_ms,
        }

    def find(self, label: str = "", elem_type: str = "", elem_id: str = "") -> Optional[VisionElement]:
        """Search elements by label (case-insensitive contains), type, or id."""
        label = (label or "").strip().lower()
        for e in self.elements:
            if elem_id and e.id == elem_id:
                return e
            if label and label in (e.label or "").lower():
                return e
            if elem_type and (
                (isinstance(e.type, ElementType) and e.type.value == elem_type.upper())
                or str(e.type).upper() == elem_type.upper()
            ):
                return e
        return None

@dataclass
class CameraObservation:
    """Structured understanding of a single camera frame (separate context)."""

    context: ContextType = ContextType.CAMERA
    status: ExecutionStatus = ExecutionStatus.OBSERVED
    scene_hash: str = ""
    summary: str = ""
    objects: List[VisionElement] = field(default_factory=list)
    frame_index: int = 0
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    degraded: bool = False
    inference_ms: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context": self.context.value,
            "status": self.status.value,
            "scene_hash": self.scene_hash,
            "summary": self.summary,
            "objects": [o.to_dict() for o in self.objects],
            "frame_index": self.frame_index,
            "confidence": round(float(self.confidence), 4),
            "timestamp": self.timestamp,
            "degraded": self.degraded,
            "inference_ms": self.inference_ms,
        }


# Confidence thresholds (spec section 26). Tuned by real tests, not magic.
CONFIDENCE_HIGH = 0.80  # >= high  -> safe candidate
CONFIDENCE_MEDIUM = 0.55  # medium  -> perform additional observation
CONFIDENCE_LOW = 0.35  # < low    -> do not act; re-observe or ask


def classify_confidence(conf: float) -> str:
    if conf >= CONFIDENCE_HIGH:
        return "high"
    if conf >= CONFIDENCE_MEDIUM:
        return "medium"
    if conf >= CONFIDENCE_LOW:
        return "low"
    return "very_low"


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