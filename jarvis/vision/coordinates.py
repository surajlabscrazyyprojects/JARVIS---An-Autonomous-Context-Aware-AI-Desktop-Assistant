"""Explicit screen-coordinate transforms for visual targets.

Vision may use a cropped/resized image while the motor uses virtual-desktop
coordinates.  Keeping the conversion here prevents accidental hard-coded
pixel assumptions and supports negative monitor origins.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoordinateTransform:
    image_width: int
    image_height: int
    desktop_x: int = 0
    desktop_y: int = 0
    desktop_width: int = 0
    desktop_height: int = 0

    def __post_init__(self):
        if self.desktop_width <= 0 or self.desktop_height <= 0:
            object.__setattr__(self, "desktop_width", self.image_width)
            object.__setattr__(self, "desktop_height", self.image_height)

    def vision_to_desktop(self, x: float, y: float) -> tuple[int, int]:
        sx = self.desktop_width / float(max(1, self.image_width))
        sy = self.desktop_height / float(max(1, self.image_height))
        return (round(self.desktop_x + x * sx), round(self.desktop_y + y * sy))

    def desktop_to_vision(self, x: float, y: float) -> tuple[int, int]:
        sx = self.image_width / float(max(1, self.desktop_width))
        sy = self.image_height / float(max(1, self.desktop_height))
        return (round((x - self.desktop_x) * sx), round((y - self.desktop_y) * sy))

    def normalized(self, x: float, y: float) -> tuple[float, float]:
        return ((x - self.desktop_x) / float(max(1, self.desktop_width)),
                (y - self.desktop_y) / float(max(1, self.desktop_height)))


__all__ = ["CoordinateTransform"]
