"""
jarvis.motor.trajectory
=======================
Trajectory generation for smooth mouse motion and freehand drawing
(spec sections 10-11, 17).

Movement is *deliberate*: eased trajectories with configurable duration,
velocity ramp-up and ramp-down. We do not inject random jitter and we do not
try to imitate biometrics — this is about natural usability and visual
quality, not evading anything (section 43).

Supported shapes for canvas interaction: line, circle, arc, rectangle,
polyline/free path.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Sequence, Tuple

Point2D = Tuple[float, float]
Tween = Callable[[float], float]


# -- easing (velocity ramp-up / ramp-down) -----------------------------------
def ease_in_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 2) / 2.0


def ease_out_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_quad(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t


TWEENS: dict = {
    "in_out": ease_in_out_quad,
    "out": ease_out_quad,
    "in": ease_in_quad,
    "linear": (lambda t: max(0.0, min(1.0, t))),
}


def tween_for(name: str) -> Tween:
    return TWEENS.get(name, ease_in_out_quad)


# -- shapes -------------------------------------------------------------------
def line_points(p0: Point2D, p1: Point2D, steps: int = 32) -> List[Point2D]:
    steps = max(2, int(steps))
    return [
        (p0[0] + (p1[0] - p0[0]) * (i / (steps - 1)),
         p0[1] + (p1[1] - p0[1]) * (i / (steps - 1)))
        for i in range(steps)
    ]


def circle_points(center: Point2D, radius: float, steps: int = 64) -> List[Point2D]:
    """Closed clockwise circle (ends where it began) for press-drag-paint."""
    steps = max(8, int(steps))
    pts = []
    for i in range(steps):
        a = 2.0 * math.pi * (i / steps)
        pts.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    pts.append(pts[0])  # closed loop
    return pts


def arc_points(center: Point2D, radius: float, start_deg: float, end_deg: float, steps: int = 48) -> List[Point2D]:
    steps = max(4, int(steps))
    start = math.radians(start_deg)
    end = math.radians(end_deg)
    return [
        (center[0] + radius * math.cos(start + (end - start) * (i / (steps - 1))),
         center[1] + radius * math.sin(start + (end - start) * (i / (steps - 1))))
        for i in range(steps)
    ]


def rectangle_points(p0: Point2D, p1: Point2D, steps_per_side: int = 16) -> List[Point2D]:
    """Clockwise rectangle outline, closed."""
    x0, y0 = p0
    x1, y1 = p1
    outline = [
        (x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0),
    ]
    pts: List[Point2D] = []
    for i in range(len(outline) - 1):
        pts.extend(line_points(outline[i], outline[i + 1], steps_per_side))
    return pts


def polyline_points(points: Sequence[Point2D], steps_per_seg: int = 24) -> List[Point2D]:
    """Free-hand / multi-segment path."""
    if not points:
        return []
    pts: List[Point2D] = []
    for i in range(len(points) - 1):
        pts.extend(line_points(points[i], points[i + 1], steps_per_seg))
    pts.append(points[-1])
    return pts


# -- trajectory object --------------------------------------------------------
@dataclass
class Trajectory:
    """A time-parameterised path with an easing profile."""

    points: List[Point2D]
    duration: float = 0.8  # total seconds
    tween: str = "in_out"
    loop: bool = False

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("trajectory needs at least two points")

    @property
    def length(self) -> float:
        total = 0.0
        for i in range(1, len(self.points)):
            total += math.hypot(self.points[i][0] - self.points[i - 1][0],
                                self.points[i][1] - self.points[i - 1][1])
        return total

    def subsample(self, count: int = 40) -> List[Point2D]:
        """Resample along the path with the easing profile applied. The tween
        maps the time index to a fraction of path *position*, so the cursor
        accelerates then decelerates (velocity ramp-up / ramp-down)."""
        count = max(3, int(count))
        n = len(self.points)
        out: List[Point2D] = []
        fn = tween_for(self.tween)
        for i in range(count):
            t = i / (count - 1)
            eased = fn(t)
            idx = eased * (n - 1)
            lo = int(math.floor(idx))
            hi = min(n - 1, lo + 1)
            frac = idx - lo
            x = self.points[lo][0] + (self.points[hi][0] - self.points[lo][0]) * frac
            y = self.points[lo][1] + (self.points[hi][1] - self.points[lo][1]) * frac
            out.append((x, y))
        return out


def build_trajectory(
    kind: str = "line",
    start: Point2D = (0, 0),
    end: Point2D = (0, 0),
    center: Point2D = (0, 0),
    radius: float = 0.0,
    points: Sequence[Point2D] = (),
    steps: int = 48,
) -> Trajectory:
    """Factory: kind in {line, circle, arc, rectangle, free}."""
    kind = (kind or "line").lower()
    if kind == "circle":
        return Trajectory(circle_points(center, radius, steps), loop=True)
    if kind == "arc":
        return Trajectory(arc_points(center, radius, 0.0, 360.0, steps), loop=False)
    if kind == "rectangle":
        return Trajectory(rectangle_points(start, end, max(8, steps // 4)), loop=True)
    if kind in ("free", "polyline"):
        return Trajectory(polyline_points(points, max(8, steps // 4)), loop=False)
    return Trajectory(line_points(start, end, steps), loop=False)


__all__ = [
    "Point2D",
    "Trajectory",
    "Tween",
    "arc_points",
    "build_trajectory",
    "circle_points",
    "ease_in_out_quad",
    "line_points",
    "polyline_points",
    "rectangle_points",
    "tween_for",
]