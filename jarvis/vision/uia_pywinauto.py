"""
jarvis.vision.uia_pywinauto
===========================
Optional pywinauto-backed UI-tree extraction (used only when pywinauto is
installed). Sibling of :mod:`jarvis.vision.uiautomation`.
"""
from __future__ import annotations

from typing import List

from jarvis.vision.contracts import Bounds, ElementSource, ElementType, Point, VisionElement

_INTERACTIVE = {
    ElementType.BUTTON, ElementType.ICON, ElementType.TEXT_FIELD, ElementType.CHECKBOX,
    ElementType.RADIO, ElementType.DROPDOWN, ElementType.MENU, ElementType.TAB,
    ElementType.SLIDER, ElementType.SCROLLBAR,
}


class PywinautoTree:
    def extract(self, max_depth: int = 8, max_elements: int = 120) -> List[VisionElement]:
        from pywinauto import Desktop  # imported lazily; only reached when pywinauto exists

        out: List[VisionElement] = []

        def walk(win, depth: int) -> None:
            if len(out) >= max_elements or depth > max_depth:
                return
            try:
                rect = win.rectangle()
                name = win.window_text()
                ctype = str(getattr(win, "friendly_class_name", "object") or "object").lower()
            except Exception:  # noqa: BLE001
                return
            w = max(0, int(rect.right - rect.left))
            h = max(0, int(rect.bottom - rect.top))
            if w > 0 and h > 0:
                etype = ElementType.BUTTON if ctype == "button" else ElementType.PANEL
                out.append(
                    VisionElement(
                        id=f"uia_{ctype}_{int(rect.left)}_{int(rect.top)}",
                        type=etype,
                        label=name or "",
                        center=Point(rect.left + w / 2.0, rect.top + h / 2.0),
                        bounds=Bounds(rect.left, rect.top, w, h),
                        interactive=etype in _INTERACTIVE,
                        confidence=0.98 if name else 0.85,
                        source=ElementSource.UIA,
                        metadata={"backend": "pywinauto", "control_type": ctype},
                    )
                )
            try:
                for child in win.children():
                    walk(child, depth + 1)
            except Exception:  # noqa: BLE001
                return

        try:
            walk(Desktop(backend="uia").window(), 0)
        except Exception:  # noqa: BLE001
            return out
        return out