"""
jarvis.motor.mouse
==================
Deterministic mouse motor controller (spec sections 10-14).

Supports absolute/relative smooth movement, configurable duration, eased
velocity profiles, click/double/right/middle, scroll, drag, press-and-hold
and release. Every call returns an execution-status result; held buttons are
tracked by the input safety watchdog so nothing can remain stuck.

The motor layer NEVER decides WHERE to click — it executes the coordinates
the planner/vision layer resolved. It does not teleport the cursor when a
smooth move is appropriate.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pyautogui

from jarvis.motor import trajectory
from jarvis.motor.watchdog import InputSafetyWatchdog
from jarvis.vision.contracts import ExecutionStatus

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01

BUTTONS = ("left", "right", "middle")
Point2D = Tuple[float, float]


def _clamp_button(button: str) -> str:
    b = (button or "left").lower()
    if b == "leftclick":
        b = "left"
    if b not in BUTTONS:
        raise ValueError(f"unsupported mouse button: {button}")
    return b


def current_position() -> Tuple[int, int]:
    x, y = pyautogui.position()
    return int(x), int(y)


# Physical primitives also used by the watchdog for emergency release.
def release_mouse_button(name: str) -> None:
    name = _clamp_button(name)
    try:
        pyautogui.mouseUp(button=name)
    except Exception:  # noqa: BLE001
        pass


def press_mouse_button(name: str) -> None:
    name = _clamp_button(name)
    pyautogui.mouseDown(button=name)


class MouseController:
    def __init__(self, watchdog: Optional[InputSafetyWatchdog] = None) -> None:
        self.watchdog = watchdog or InputSafetyWatchdog()

    @staticmethod
    def _result(ok: bool, status: ExecutionStatus, summary: str, **data: Any) -> Dict[str, Any]:
        return {"ok": ok, "status": status.value, "summary": summary, "data": data}

    # -- smooth movement ------------------------------------------------------
    def move(self, x: float, y: float, duration: float = 0.35, tween: str = "in_out") -> Dict[str, Any]:
        x, y = int(x), int(y)
        if not (0 <= x <= pyautogui.size().width and 0 <= y <= pyautogui.size().height):
            return self._result(False, ExecutionStatus.FAILED,
                                f"target ({x},{y}) outside screen", x=x, y=y)
        try:
            pyautogui.moveTo(x, y, duration=max(0.05, duration), tween=trajectory.tween_for(tween))
            return self._result(True, ExecutionStatus.OBSERVED, f"moved to {x},{y}", x=x, y=y)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, ExecutionStatus.FAILED, f"move failed: {exc}")

    def move_relative(self, dx: float, dy: float, duration: float = 0.2) -> Dict[str, Any]:
        cx, cy = current_position()
        return self.move(int(cx + dx), int(cy + dy), duration=duration)

    # -- clicks ---------------------------------------------------------------
    def click(self, x: Optional[float] = None, y: Optional[float] = None, button: str = "left", count: int = 1) -> Dict[str, Any]:
        button = _clamp_button(button)
        target = (int(x), int(y)) if x is not None and y is not None else None
        try:
            if target is not None:
                pyautogui.click(target[0], target[1], clicks=count, interval=0.03, button=button)
            else:
                pyautogui.click(clicks=count, interval=0.03, button=button)
            return self._result(True, ExecutionStatus.OBSERVED,
                                f"clicked {button} at {target or 'cursor'}", button=button)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, ExecutionStatus.FAILED, f"click failed: {exc}")

    def double_click(self, x: Optional[float] = None, y: Optional[float] = None) -> Dict[str, Any]:
        return self.click(x, y, button="left", count=2)

    def right_click(self, x: Optional[float] = None, y: Optional[float] = None) -> Dict[str, Any]:
        return self.click(x, y, button="right", count=1)

    def middle_click(self, x: Optional[float] = None, y: Optional[float] = None) -> Dict[str, Any]:
        return self.click(x, y, button="middle", count=1)

    # -- scroll -----------------------------------------------------------------
    def scroll(self, amount: int, x: Optional[float] = None, y: Optional[float] = None) -> Dict[str, Any]:
        try:
            if x is not None and y is not None:
                pyautogui.scroll(int(amount), int(x), int(y))
            else:
                pyautogui.scroll(int(amount))
            return self._result(True, ExecutionStatus.OBSERVED, f"scrolled {int(amount)}")
        except Exception as exc:  # noqa: BLE001
            return self._result(False, ExecutionStatus.FAILED, f"scroll failed: {exc}")
# -- drag / press-and-hold -------------------------------------------------
    def drag(self, x1: float, y1: float, x2: float, y2: float, button: str = "left", duration: float = 0.6) -> Dict[str, Any]:
        button = _clamp_button(button)
        pts = trajectory.line_points((x1, y1), (x2, y2), steps=40)
        res = self._press_and_trace(pts, button=button, step_duration=max(0.01, duration / 40.0))
        if res.get("ok"):
            return self._result(True, ExecutionStatus.OBSERVED,
                                f"dragged ({x1},{y1})->({x2},{y2})", x1=x1, y1=y1, x2=x2, y2=y2)
        return res

    def press_and_hold(self, x: float, y: float, button: str = "left") -> Dict[str, Any]:
        button = _clamp_button(button)
        try:
            self.move(int(x), int(y), duration=0.25)
            press_mouse_button(button)
            self.watchdog.press("mouse", button)
            return self._result(True, ExecutionStatus.EXECUTING, f"holding {button} at ({x},{y})")
        except Exception as exc:  # noqa: BLE001
            return self._result(False, ExecutionStatus.FAILED, f"press failed: {exc}")

    def release(self, button: Optional[str] = None) -> Dict[str, Any]:
        if button is None:
            # Release every tracked mouse button (idempotent).
            held = list(self.watchdog.held_buttons())
            for b in held:
                release_mouse_button(b)
                self.watchdog.release("mouse", b)
            return self._result(True, ExecutionStatus.OBSERVED, "released held mouse buttons", released=held)
        button = _clamp_button(button)
        release_mouse_button(button)
        self.watchdog.release("mouse", button)
        return self._result(True, ExecutionStatus.OBSERVED, f"released {button}")

    def _press_and_trace(
        self,
        pts: Sequence[Point2D],
        button: str = "left",
        step_duration: float = 0.02,
        dwell: float = 0.05,
    ) -> Dict[str, Any]:
        """Press at the first point, traverse the eased path, release (13/14)."""
        if not pts:
            return self._result(False, ExecutionStatus.FAILED, "empty trajectory")
        try:
            pyautogui.moveTo(int(pts[0][0]), int(pts[0][1]), duration=0.2, tween=trajectory.ease_in_out_quad)
            time.sleep(dwell)
            press_mouse_button(button)
            self.watchdog.press("mouse", button)
            # Traverse each point in micro-movements; no vision calls per point.
            for px, py in pts[1:]:
                pyautogui.moveTo(int(px), int(py), duration=step_duration, tween=trajectory.ease_in_out_quad)
            time.sleep(dwell)
            release_mouse_button(button)
            self.watchdog.release("mouse", button)
            return self._result(True, ExecutionStatus.OBSERVED,
                                f"traced path ({len(pts)} points, button={button})")
        except Exception as exc:  # noqa: BLE001
            release_mouse_button(button)
            self.watchdog.release("mouse", button)
            return self._result(False, ExecutionStatus.FAILED, f"trace failed: {exc}")

    # -- drawing -----------------------------------------------------------------
    def trace_shape(
        self,
        kind: str,
        center: Optional[Tuple[float, float]] = None,
        radius: float = 0.0,
        start: Optional[Tuple[float, float]] = None,
        end: Optional[Tuple[float, float]] = None,
        points: Optional[Sequence[Point2D]] = None,
        button: str = "left",
        step_duration: float = 0.02,
        tween: str = "in_out",
    ) -> Dict[str, Any]:
        """Execute a canvas drawing/erasing stroke (spec sections 17-18)."""
        traj = trajectory.build_trajectory(
            kind=kind,
            start=start or (0.0, 0.0),
            end=end or (0.0, 0.0),
            center=center or (0.0, 0.0),
            radius=radius or 0.0,
            points=list(points or []),
        )
        path = traj.subsample(count=max(24, int(traj.length / 6)))
        res = self._press_and_trace(path, button=_clamp_button(button), step_duration=step_duration)
        if not res.get("ok"):
            return res
        return self._result(True, ExecutionStatus.OBSERVED,
                            f"drew {kind} path ({len(path)} points)", kind=kind)


__all__ = ["MouseController", "Point2D", "current_position", "press_mouse_button", "release_mouse_button"]