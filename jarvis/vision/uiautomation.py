"""
jarvis.vision.uiautomation
==========================
Deterministic UI-tree adapter (spec: LEVEL 2 accessibility/UI tree and section
38 "prefer deterministic UI automation over vision").

Two backends are tried, lazily:
  1. the ``uiautomation`` pip package (light UIA wrapper, no admin rights)
  2. pywinauto UIA/win32 backends

When neither is installed we degrade gracefully: the adapter reports
``available = False`` and the analyzer falls back to Win32 metadata + Gemma
vision. The adapter is a strict preference, never a crash point.

Element coordinates are normalized to screen pixels so downstream motor
planning does not care where they came from.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from jarvis.vision.contracts import Bounds, ElementSource, ElementType, Point, VisionElement

log = logging.getLogger("jarvis.vision.uia")

# UIA ControlType -> our ElementType vocabulary
_CONTROL_TYPES = {
    "button": ElementType.BUTTON,
    "icon": ElementType.ICON,
    "edit": ElementType.TEXT_FIELD,
    "checkbox": ElementType.CHECKBOX,
    "radio": ElementType.RADIO,
    "combo": ElementType.DROPDOWN,
    "menuitem": ElementType.MENU,
    "tabitem": ElementType.TAB,
    "slider": ElementType.SLIDER,
    "scrollbar": ElementType.SCROLLBAR,
    "list": ElementType.LIST,
    "table": ElementType.TABLE,
    "image": ElementType.IMAGE,
    "pane": ElementType.PANEL,
    "group": ElementType.PANEL,
    "window": ElementType.WINDOW,
    "toolbar": ElementType.TOOLBAR,
    "canvas": ElementType.CANVAS,
    "dialog": ElementType.DIALOG,
    "text": ElementType.OBJECT,
    "document": ElementType.PANEL,
}

_INTERACTIVE = {
    ElementType.BUTTON, ElementType.ICON, ElementType.TEXT_FIELD, ElementType.CHECKBOX,
    ElementType.RADIO, ElementType.DROPDOWN, ElementType.MENU, ElementType.TAB,
    ElementType.SLIDER, ElementType.SCROLLBAR,
}


class UIAutomationAdapter:
    def __init__(self) -> None:
        self._backend = None
        self._backend_name = ""
        self._load_error: Optional[str] = None

    # -- backend discovery --------------------------------------------------
    def _discover(self):
        if self._backend is not None:
            return self._backend
        if self._load_error is not None:
            return None
        try:
            import uiautomation as _uia  # pip package: uiautomation

            self._backend = _uia
            self._backend_name = "uiautomation"
            return self._backend
        except Exception as exc:  # noqa: BLE001
            self._load_error = str(exc)
        try:
            import pywinauto  # noqa: F401  (not installed by default here)

            self._backend_name = "pywinauto"
            from jarvis.vision.uia_pywinauto import PywinautoTree  # type: ignore
            self._backend = PywinautoTree()
            return self._backend
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"{self._load_error}; pywinauto: {exc}"
        self._backend = None
        return None

    @property
    def available(self) -> bool:
        return self._discover() is not None

    @property
    def backend_name(self) -> str:
        self._discover()
        return self._backend_name

    # -- tree extraction ----------------------------------------------------
    def extract(self, max_depth: int = 8, max_elements: int = 120) -> List[VisionElement]:
        """Walk the active window's UI tree and return control elements.

        Empty list means: no deterministic tree (caller should fall back to
        vision). Never raises for environment issues."""
        backend = self._discover()
        if backend is None:
            return []
        try:
            if self._backend_name == "uiautomation":
                return self._extract_uiautomation(backend, max_depth, max_elements)
            return self._extract_pywinauto(backend, max_depth, max_elements)
        except Exception as exc:  # noqa: BLE001
            log.warning("UIA tree extraction failed (%s): %s", self._backend_name, exc)
            self._load_error = str(exc)
            self._backend = None
            return []

    def _extract_uiautomation(self, uia, max_depth: int, max_elements: int) -> List[VisionElement]:
        root = uia.GetRootControl()
        try:
            focus = uia.GetFocusedControl()
        except Exception:  # noqa: BLE001
            focus = None
        target = focus or root
        out: List[VisionElement] = []

        def walk(control, depth: int) -> None:
            if len(out) >= max_elements or depth > max_depth:
                return
            try:
                name = control.Name or ""
                ctype = (control.ControlTypeName or "").replace("Control", "").lower()
                rect = control.BoundingRectangle
            except Exception:  # noqa: BLE001
                return
            if rect is not None and (rect.width() > 0 and rect.height() > 0):
                out.append(self._to_element(name, ctype, rect.left, rect.top, rect.width(), rect.height()))
            try:
                for child in control.GetChildren():
                    walk(child, depth + 1)
            except Exception:  # noqa: BLE001
                return

        walk(target, 0)
        return self._dedupe(out)

    def _extract_pywinauto(self, backend, max_depth: int, max_elements: int) -> List[VisionElement]:
        return backend.extract(max_depth, max_elements)

    @staticmethod
    def _to_element(name: str, ctype: str, left: int, top: int, w: int, h: int) -> VisionElement:
        etype = _CONTROL_TYPES.get(ctype, ElementType.OBJECT)
        el = VisionElement(
            id=f"uia_{ctype}_{int(left)}_{int(top)}",
            type=etype,
            label=name or "",
            center=Point(left + w / 2.0, top + h / 2.0),
            bounds=Bounds(left, top, w, h),
            interactive=etype in _INTERACTIVE,
            enabled=True,
            confidence=0.99 if name else 0.9,  # deterministic metadata >> vision
            source=ElementSource.UIA,
            metadata={"backend": "uia", "control_type": ctype},
        )
        return el

    @staticmethod
    def _dedupe(elements: List[VisionElement]) -> List[VisionElement]:
        seen = set()
        out = []
        for e in elements:
            key = (int(e.bounds.x), int(e.bounds.y), int(e.bounds.width), int(e.bounds.height), e.label)
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
        return out


_UI_ADAPTER: Optional[UIAutomationAdapter] = None


def get_uia_adapter() -> UIAutomationAdapter:
    """Process-wide singleton adapter (lazy, cheap)."""
    global _UI_ADAPTER
    if _UI_ADAPTER is None:
        _UI_ADAPTER = UIAutomationAdapter()
    return _UI_ADAPTER