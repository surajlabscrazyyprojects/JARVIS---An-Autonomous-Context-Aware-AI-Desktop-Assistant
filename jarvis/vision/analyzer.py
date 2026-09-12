"""
jarvis.vision.analyzer
======================
VisionAnalyzer — the "vision tool contract" facade (spec section 33):

    vision.analyze_screen()   -> ScreenObservation
    vision.analyze_region()   -> ScreenObservation
    vision.find_element()     -> VisionElement
    vision.compare_state()    -> diff dict (delegated to verifier)

The analyzer implements adaptive observation (spec section 6) — LEVEL 0..4 —
and always uses the cheapest reliable mechanism first:

    LEVEL 1 (window metadata)          -- always available, no model
    LEVEL 2 (UI tree via UIA)          -- preferred where available
    LEVEL 3 (targeted region vision)   -- only when needed
    LEVEL 4 (full-screen vision)       -- only when needed

Screen-change detection (section 23) lets the analyzer REUSE a fresh enough
observation instead of re-running expensive inference (section 60).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from jarvis.vision import capture, win32meta
from jarvis.vision.contracts import (
    Bounds,
    ContextType,
    ElementSource,
    ElementType,
    ExecutionStatus,
    ObservationLevel,
    Point,
    ScreenObservation,
    VisionElement,
)
from jarvis.vision.gemma import GemmaVision, GemmaVisionError
from jarvis.vision.uiautomation import UIAutomationAdapter, get_uia_adapter
from jarvis.vision.verifier import VerificationEngine
from jarvis.vision.visual_memory import VisualMemory
from jarvis.vision.privacy import VisionMode, VisionPrivacy
from jarvis.vision.ocr import OCRManager

log = logging.getLogger("jarvis.vision.analyzer")

# Observation cache lifetime: reuse a full analysis for this long.
OBSERVATION_CACHE_AGE = 4.0
class VisionAnalyzer:
    def __init__(
        self,
        memory: Optional[VisualMemory] = None,
        gemma: Optional[GemmaVision] = None,
        uia: Optional[UIAutomationAdapter] = None,
        verifier: Optional[VerificationEngine] = None,
        privacy: Optional[VisionPrivacy] = None,
        ocr: Optional[OCRManager] = None,
        cache_age: float = OBSERVATION_CACHE_AGE,
    ) -> None:
        self.memory = memory or VisualMemory()
        self.gemma = gemma or GemmaVision()
        self.uia = uia if uia is not None else get_uia_adapter()
        self.verifier = verifier or VerificationEngine()
        self.privacy = privacy or VisionPrivacy()
        self.ocr = ocr or OCRManager()
        self.cache_age = cache_age
        self._last_observation: Optional[ScreenObservation] = None
        self._last_level = ObservationLevel.NONE

    # -- level selection -----------------------------------------------------
    def select_level(self, goal: str = "", force_level: Optional[int] = None, ui_available: Optional[bool] = None) -> ObservationLevel:
        """Spec section 6: only escalate when necessary."""
        if force_level is not None:
            try:
                return ObservationLevel(int(force_level))
            except (TypeError, ValueError):
                pass
        g = (goal or "").lower()
        if not g:
            return ObservationLevel.WINDOW_META
        if any(k in g for k in ("what's on", "what is on", "what do you see", "describe screen", "show on screen")):
            return ObservationLevel.FULL_SCREEN
        if any(k in g for k in ("draw", "paint", "erase", "canvas", "select the red")):
            return ObservationLevel.REGION
        if ui_available is not None and not ui_available:
            return ObservationLevel.WINDOW_META
        return ObservationLevel.UI_TREE
# -- public contracts -----------------------------------------------------
    def analyze_screen(
        self,
        level: Optional[int] = None,
        goal: str = "",
        force: bool = False,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> ScreenObservation:
        """Structured observation of the current screen (adaptive level)."""
        t0 = time.perf_counter()
        if not self.privacy.enabled:
            # Do not even query/capture the desktop while vision is disabled.
            obs = ScreenObservation(
                observation_level=ObservationLevel.NONE,
                status=ExecutionStatus.CANCELLED,
                summary="SCREEN_VISION_DISABLED",
                degraded=True,
                timestamp=time.time(),
            )
            self._last_observation = None
            self.memory.invalidate_target("screen vision disabled")
            return obs
        meta = win32meta.get_active_window_info()
        size = meta.get("screen_size") or win32meta.screen_size()
        cursor = meta.get("cursor") or Point()
        bounds = meta.get("bounds") or Bounds()

        # Fresh-cache reuse: skip expensive work when nothing meaningful
        # changed on screen (spec section 23 / 60).
        if (not force) and self._last_observation is not None:
            if level is None and self._last_level >= ObservationLevel.UI_TREE:
                hash_now, _ = capture.capture_screen_hash()
                if hash_now == self.memory.screen_hash and (time.time() - self._last_observation.timestamp) < self.cache_age:
                    obs = self._last_observation
                    obs.cursor = cursor
                    obs.window_title = meta.get("title", "") or obs.window_title
                    obs.reused = True
                    self.memory.record(obs)
                    return obs

        chosen = self.select_level(goal, force_level=level, ui_available=self.uia.available)
        self._last_level = chosen
        obs = ScreenObservation(
            observation_level=chosen,
            application=meta.get("application", ""),
            window_title=meta.get("title", ""),
            window_bounds=bounds,
            screen_size=size,
            cursor=cursor,
            timestamp=time.time(),
        )

        img = None
        if chosen >= ObservationLevel.WINDOW_META:
            # Capture only once for anything above L0.
            img, capture_ms = capture.capture_screen()
            obs.screen_hash = capture.image_hash(img)
            obs.capture_ms = capture_ms

        if chosen == ObservationLevel.UI_TREE:
            elements = self.uia.extract() if self.uia.available else []
            if elements:
                obs.elements = elements
                obs.application = obs.application or self._app_from_elements(elements)
            elif self.gemma.is_available():
                self._apply_vision(obs, img, goal=goal, region=region)
            else:
                obs.degraded = True
                obs.summary = "VISION_DEGRADED - deterministic tree and gemma3:4b unavailable"

        elif chosen in (ObservationLevel.FULL_SCREEN, ObservationLevel.REGION):
            if self.gemma.is_available():
                self._apply_vision(obs, img, goal=goal, region=region)
            else:
                obs.degraded = True
                obs.summary = "VISION_DEGRADED - gemma3:4b unavailable; deterministic metadata only"

        obs.inference_ms = getattr(self.gemma, "last_inference_ms", 0)
        obs.meta["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        self._last_observation = obs
        self.memory.record(obs)
        return obs

    def ocr_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
        """Run optional local OCR for the current screen/region only."""
        if not self.privacy.enabled:
            return {"ok": False, "text": "", "items": [], "error": "SCREEN_VISION_DISABLED"}
        img, capture_ms = capture.capture_screen(region)
        result = self.ocr.extract(img)
        if not result.get("ok") and self.uia.available:
            # Accessibility text is a deterministic local fallback when the
            # optional Tesseract binary is not installed.
            items = []
            for el in self.uia.extract():
                if not el.label:
                    continue
                items.append({
                    "text": el.label,
                    "bbox": [int(el.bounds.x), int(el.bounds.y), int(el.bounds.width), int(el.bounds.height)],
                    "confidence": float(el.confidence),
                    "source": "uia",
                })
            if items:
                result = {"ok": True, "text": " ".join(item["text"] for item in items), "items": items,
                          "engine": "uia_text_fallback"}
        result["capture_ms"] = capture_ms
        return result

    def analyze_region(
        self,
        region: Tuple[int, int, int, int],
        goal: str = "",
        force: bool = False,
    ) -> ScreenObservation:
        """LEVEL 3: targeted screenshot region — no full-screen inference."""
        img, capture_ms = capture.capture_screen(region)
        obs = ScreenObservation(
            observation_level=ObservationLevel.REGION,
            screen_hash=capture.image_hash(img),
            capture_ms=capture_ms,
            timestamp=time.time(),
        )
        meta = win32meta.get_active_window_info()
        obs.application = meta.get("application", "")
        obs.window_title = meta.get("title", "")
        obs.window_bounds = meta.get("bounds") or Bounds()
        obs.screen_size = meta.get("screen_size") or win32meta.screen_size()
        obs.cursor = meta.get("cursor") or Point()
        if not force and self._last_observation is not None and self._last_observation.screen_hash == obs.screen_hash:
            obs.reused = True
            obs.summary = self._last_observation.summary
            obs.elements = self._last_observation.elements
            obs.inference_ms = self._last_observation.inference_ms
            self.memory.record(obs)
            return obs
        if self.gemma.is_available():
            self._apply_vision(obs, img, goal=goal, region=region)
        else:
            obs.degraded = True
            obs.summary = "VISION_DEGRADED - gemma3:4b unavailable"
        self._last_observation = obs
        self.memory.record(obs)
        return obs

    # -- element acquisition --------------------------------------------------
    def find_element(
        self,
        label: str = "",
        elem_type: str = "",
        elem_id: str = "",
        goal: str = "",
    ) -> Optional[VisionElement]:
        """Target acquisition (spec section 9). Deterministic first, vision
        fallback, memory reuse, stale-target protection (section 25)."""
        # 1) fresh memory (avoids re-analysis; section 60)
        el = self.memory.find(label=label, elem_type=elem_type, elem_id=elem_id)
        if el is not None and not self.memory.target_is_stale:
            return el
        if el is not None:
            self.memory.invalidate_target("stale target")

        # 2) deterministic UI tree (section 63 — do not ask Gemma for what UIA knows)
        if self.uia.available:
            elements = self.uia.extract()
            for e in elements:
                if label and label.lower() in (e.label or "").lower():
                    self.memory.acquire_target(e)
                    return e
                if elem_type and str(getattr(e.type, "value", e.type)).upper() == elem_type.upper():
                    self.memory.acquire_target(e)
                    return e

        # 3) vision fallback (full-screen analysis focused on the label)
        if self.gemma.is_available():
            obs = self.analyze_screen(level=int(ObservationLevel.FULL_SCREEN), goal=goal or label, force=True)
            el = obs.find(label=label, elem_type=elem_type, elem_id=elem_id)
            if el is not None:
                self.memory.acquire_target(el)
                return el
        return None

    # -- internals -------------------------------------------------------------
    def _apply_vision(self, obs: ScreenObservation, img, goal: str, region: Optional[tuple]) -> None:
        if img is None:
            img, _ = capture.capture_screen()
            obs.screen_hash = capture.image_hash(img)
        try:
            data = self.gemma.analyze_screen(img, region=region, goal=goal)
        except GemmaVisionError as exc:
            log.warning("Gemma screen analysis degraded: %s", exc)
            obs.degraded = True
            obs.summary = f"VISION_DEGRADED - {exc}"
            return
        obs.summary = data.get("screen_summary", "")
        obs.window_title = data.get("window_title", "") or obs.window_title
        obs.application = data.get("application", "") or obs.application
        obs.elements = [VisionAnalyzer._restore(e) for e in data.get("elements", []) if e]

    @staticmethod
    def _restore(d: Dict[str, Any]) -> Optional[VisionElement]:
        """Rehydrate a VisionElement from its to_dict() form."""
        try:
            etype = ElementType(str(d.get("type", "OBJECT")).upper())
        except ValueError:
            etype = ElementType.OBJECT
        return VisionElement(
            id=d.get("id", ""),
            type=etype,
            label=d.get("label", ""),
            center=Point(float(d.get("center", {}).get("x", 0)), float(d.get("center", {}).get("y", 0))),
            bounds=Bounds(
                float(d.get("bounds", {}).get("x", 0)),
                float(d.get("bounds", {}).get("y", 0)),
                float(d.get("bounds", {}).get("width", 0)),
                float(d.get("bounds", {}).get("height", 0)),
            ),
            interactive=bool(d.get("interactive", False)),
            confidence=float(d.get("confidence", 0) or 0),
            source=ElementSource.VISION,
        )

    @staticmethod
    def _app_from_elements(elements: List[VisionElement]) -> str:
        for e in elements:
            name = str(getattr(e.type, "value", e.type)).upper()
            if name == "WINDOW" and e.label:
                title = e.label
                if "." in title:
                    return title.split(".")[0].lower()
        return ""

    def compare_state(self, other: Optional[ScreenObservation] = None) -> Dict[str, Any]:
        cur = self.analyze_screen(force=True)
        base = other or self._last_observation
        if base is None:
            return {"error": "no baseline observation"}
        return self.verifier.compare_state(base, cur)

    @property
    def context(self) -> ContextType:
        return ContextType.SCREEN


__all__ = ["OBSERVATION_CACHE_AGE", "VisionAnalyzer"]
