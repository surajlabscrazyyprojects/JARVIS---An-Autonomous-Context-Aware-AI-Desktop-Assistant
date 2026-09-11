"""
jarvis.motor.planner
====================
Motor planner (spec sections 3, 9, 12-14, 17-18).

It answers "HOW do I physically perform this action?" given a resolved target
(a VisionElement) or an explicit drawing request:
   * picks the safe click point (prefer the control center, clamped to bounds)
   * refuses clicks below the confidence threshold (never blind-act)
   * plans drag/drop and drawing strokes with the robot's checker-free,
     deliberate motion

The planner never resolves WHAT to click — that is the vision layer's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from jarvis.motor.mouse import MouseController
from jarvis.motor.trajectory import line_points
from jarvis.motor.watchdog import InputSafetyWatchdog
from jarvis.vision.contracts import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    ExecutionStatus,
    VisionElement,
)


@dataclass
class MotorPlan:
    action: str  # "click" | "drag" | "draw" | "move"
    target: Optional[Tuple[float, float]] = None
    button: str = "left"
    shape_kind: str = ""
    shapes: int = 1
    options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": list(self.target) if self.target else None,
            "button": self.button,
            "shape_kind": self.shape_kind,
            "options": self.options,
        }


class MotorPlanner:
    def __init__(
        self,
        mouse: Optional[MouseController] = None,
        watchdog: Optional[InputSafetyWatchdog] = None,
    ) -> None:
        self.mouse = mouse or MouseController(watchdog=watchdog or InputSafetyWatchdog())
        self.watchdog = self.mouse.watchdog

    # -- target point --------------------------------------------------------
    @staticmethod
    def safe_click_point(element: VisionElement) -> Tuple[float, float]:
        """Prefer the control center; clamp into its bounds. Shrink the click
        point inward for very large controls so we never hit the very edge."""
        c = element.center
        b = element.bounds
        x = max(b.x + 2, min(c.x, b.x + b.width - 2))
        y = max(b.y + 2, min(c.y, b.y + b.height - 2))
        return (x, y)

    def plan_click(self, element: Optional[VisionElement] = None, x: float = 0, y: float = 0) -> MotorPlan:
        """Motor plan for a single click at an element (or explicit x,y)."""
        if element is not None:
            if element.confidence < CONFIDENCE_MEDIUM:
                raise ValueError(
                    f"target confidence too low ({element.confidence:.2f}) to act; re-observe"
                )
            tx, ty = self.safe_click_point(element)
            plan = MotorPlan(action="click", target=(tx, ty), button="left", options={"element_id": element.id})
            return plan
        return MotorPlan(action="click", target=(int(x), int(y)), button="left")

    def plan_move(self, x: float, y: float) -> MotorPlan:
        return MotorPlan(action="move", target=(int(x), int(y)))

    def plan_drag(self, source: Optional[VisionElement], dest: Optional[VisionElement],
                  x1: float = 0, y1: float = 0, x2: float = 0, y2: float = 0) -> MotorPlan:
        if source is not None and dest is not None:
            sx, sy = self.safe_click_point(source)
            dx, dy = self.safe_click_point(dest)
        else:
            sx, sy, dx, dy = int(x1), int(y1), int(x2), int(y2)
        return MotorPlan(action="drag", target=(sx, sy), options={"destination": (dx, dy)})

    def plan_drawing(
        self,
        kind: str,
        bounds_or: Optional[Any] = None,
        center: Optional[Tuple[float, float]] = None,
        radius: Optional[float] = None,
        start: Optional[Tuple[float, float]] = None,
        end: Optional[Tuple[float, float]] = None,
        shapes: int = 1,
    ) -> MotorPlan:
        """Plan a drawing/erasing stroke. A canvas bounds can be provided to
        derive a safe center and radius automatically."""
        opts: Dict[str, Any] = {"kind": kind}
        if bounds_or is not None and hasattr(bounds_or, "center"):
            bc = bounds_or.center
            r = max(10.0, min(bounds_or.width, bounds_or.height) * 0.3)
            opts["center"] = (bc.x, bc.y)
            opts["radius"] = r
        if center:
            opts["center"] = (float(center[0]), float(center[1]))
        if radius:
            opts["radius"] = float(radius)
        if start:
            opts["start"] = (float(start[0]), float(start[1]))
        if end:
            opts["end"] = (float(end[0]), float(end[1]))
        return MotorPlan(action="draw", shape_kind=kind, shapes=int(shapes or 1), options=opts)

    # -- execution ------------------------------------------------------------
    def execute(self, plan: MotorPlan, keyboard: Any = None) -> Dict[str, Any]:
        """Execute a resolved MotorPlan against the real mouse/keyboard."""
        if plan.action == "click":
            return self.mouse.click(plan.target[0], plan.target[1], button=plan.button)
        if plan.action == "move":
            return self.mouse.move(plan.target[0], plan.target[1])
        if plan.action == "drag":
            dest = plan.options.get("destination", (0, 0))
            return self.mouse.drag(plan.target[0], plan.target[1], dest[0], dest[1], button=plan.button)
        if plan.action == "draw":
            return self.mouse.trace_shape(
                kind=plan.shape_kind,
                center=plan.options.get("center"),
                radius=plan.options.get("radius", 0.0),
                start=plan.options.get("start"),
                end=plan.options.get("end"),
                button=plan.button,
            )
        return {"ok": False, "status": ExecutionStatus.FAILED.value, "summary": f"unknown plan {plan.action}"}


__all__ = ["MotorPlan", "MotorPlanner"]