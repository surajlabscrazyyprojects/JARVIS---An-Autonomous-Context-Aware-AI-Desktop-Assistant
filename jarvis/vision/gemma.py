"""
jarvis.vision.gemma
===================
Gemma 3 4B vision component via Ollama (``gemma3:4b``).

Gemma's job is strictly to INTERPRET visual information and return structured
JSON. It NEVER moves the mouse — the deterministic motor layer does that
(spec sections 2-3). Structured output is enforced with a JSON-only prompt and
robust parsing (code fences, trailing prose, stray commas).

Model failure never crashes JARVIS: callers receive ``degraded=True`` and the
analyzer falls back to deterministic UI automation / window metadata, or asks
the user when nothing safe can be resolved (spec section 41).
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, Optional

from PIL import Image

from jarvis.ai.ollama import OllamaAdapter
from jarvis.vision import capture
from jarvis.vision.contracts import (
    Bounds,
    ElementSource,
    ElementType,
    Point,
    VisionElement,
)

log = logging.getLogger("jarvis.vision.gemma")

DEFAULT_MODEL = "gemma3:4b"

_SCREEN_SYSTEM = (
    "You are the vision module of a careful computer operator. Analyze the "
    "provided screenshot image and return ONLY a single JSON object (no "
    "markdown, no prose) with this exact shape:\n"
    '{"application": string, "window_title": string, "screen_summary": string, '
    '"elements": [{"id": string, "type": one of '
    "BUTTON,ICON,TEXT_FIELD,CHECKBOX,RADIO,DROPDOWN,MENU,TAB,SLIDER,SCROLLBAR,"
    "LIST,TABLE,IMAGE,CANVAS,DIALOG,WINDOW,TOOLBAR,PANEL,OBJECT,CURSOR_TARGET"
    ', "label": string, "center": {"x": int, "y": int}, '
    '"bounds": {"x": int, "y": int, "width": int, "height": int}, '
    '"interactive": bool, "confidence": float 0..1}]}\n'
    "coordinates are screen pixels in the image. Only list elements you are "
    "reasonably confident exist. Prefer short labels (button text)."
)

_CAMERA_SYSTEM = (
    "You are the vision module of a computer assistant analyzing a CAMERA "
    "frame (not a screen). Return ONLY a JSON object:\n"
    '{"summary": string, "objects": [{"id":string,"label":string,'
    '"center":{"x":int,"y":int},"bounds":{"x":int,"y":int,"width":int,"height":int},'
    '"confidence":float}]}\n'
    "Enumerate distinct visible objects and note people presence if visible."
)


class GemmaVisionError(Exception):
    pass


class GemmaVision:
    def __init__(
        self,
        ollama: Optional[OllamaAdapter] = None,
        model: str = DEFAULT_MODEL,
        max_dim: int = capture.DEFAULT_MAX_ANALYSIS_DIM,
        quality: int = 80,
        timeout: int = 120,
    ) -> None:
        self.ollama = ollama or OllamaAdapter()
        self.model = model
        self.max_dim = max_dim
        self.quality = quality
        self.timeout = timeout
        self._available: Optional[bool] = None
        self._last_inference_ms: int = 0

    # -- availability -------------------------------------------------------
    def is_available(self) -> bool:
        """Lazy availability probe (ollama reachable AND gemma3 present)."""
        if self._available is None:
            try:
                self._available = self.ollama.model_available(self.model)
            except Exception as exc:  # noqa: BLE001
                log.debug("Gemma availability probe failed: %s", exc)
                self._available = False
        return self._available

    def reset_availability(self) -> None:
        self._available = None

    # -- public structured entry points -------------------------------------
    def analyze_screen(self, image: Image.Image, region: Optional[tuple] = None, goal: str = "") -> Dict[str, Any]:
        if region is not None:
            image = capture.region_image(image, region)
        prompt = self._build_screen_user_prompt(image.size, goal)
        raw = self._ask_structured(_SCREEN_SYSTEM, prompt, image)
        data = self._parse_json(raw)
        obs = self._normalise_screen(data, image.size, region=region, raw=raw)
        return obs

    def analyze_camera(self, image: Image.Image, goal: str = "") -> Dict[str, Any]:
        prompt = (f"Analyze this camera frame. {goal}").strip() + " Return the JSON object exactly as specified."
        raw = self._ask_structured(_CAMERA_SYSTEM, prompt, image)
        data = self._parse_json(raw)
        obs = self._normalise_camera(data, image.size)
        return obs

    @staticmethod
    def _build_screen_user_prompt(size: tuple, goal: str) -> str:
        base = (
            f"The screenshot is {size[0]}x{size[1]} pixels (screen coordinates). "
            "Identify the currently visible UI and controls."
        )
        if goal:
            base += f" Focus especially on elements relevant to: {goal}."
        base += " Return only the JSON object."
        return base
# -- transport ------------------------------------------------------------
    def _ask_structured(self, system: str, user: str, image: Image.Image) -> str:
        if not self.is_available():
            raise GemmaVisionError("gemma3:4b not available via Ollama")
        t0 = time.perf_counter()
        b64 = capture.encode_jpeg_base64(image, max_dim=self.max_dim, quality=self.quality)
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": system + "\n\n" + user},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}
        ]
        try:
            text = self.ollama.chat(messages, model=self.model, role="vision", timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            raise GemmaVisionError(f"gemma vision call failed: {exc}") from exc
        self._last_inference_ms = int((time.perf_counter() - t0) * 1000)
        return text or "{}"

    @property
    def last_inference_ms(self) -> int:
        return self._last_inference_ms

    # -- robust JSON parsing -------------------------------------------------
    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        if not raw or not raw.strip():
            return {}
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        try:
            cleaned = re.sub(r",\s*([}\]])", r"\1", text)
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            log.warning("Could not parse Gemma JSON: %s", exc)
            return {}

    # -- normalisation --------------------------------------------------------
    @staticmethod
    def _normalise_screen(data: Dict[str, Any], img_size: tuple, region: Optional[tuple], raw: str) -> Dict[str, Any]:
        elements = []
        for i, e in enumerate(data.get("elements") or []):
            el = GemmaVision._element_from_dict(i, e)
            if el is not None:
                if region:
                    el.center.x += region[0]
                    el.center.y += region[1]
                    el.bounds.x += region[0]
                    el.bounds.y += region[1]
                elements.append(el.to_dict())
        return {
            "application": str(data.get("application") or ""),
            "window_title": str(data.get("window_title") or ""),
            "screen_summary": str(data.get("screen_summary") or ""),
            "elements": elements,
            "raw": raw,
        }

    @staticmethod
    def _element_from_dict(i: int, e: Dict[str, Any]) -> Optional[VisionElement]:
        try:
            center = e.get("center") or {}
            bounds = e.get("bounds") or {}
            etype = str(e.get("type") or "OBJECT").upper()
            if etype not in ElementType._value2member_map_:
                etype = "OBJECT"
            return VisionElement(
                id=str(e.get("id") or f"vis_{i}"),
                type=ElementType(etype),
                label=str(e.get("label") or ""),
                center=Point(float(center.get("x", 0)), float(center.get("y", 0))),
                bounds=Bounds(
                    float(bounds.get("x", 0)),
                    float(bounds.get("y", 0)),
                    float(bounds.get("width", 0)),
                    float(bounds.get("height", 0)),
                ),
                interactive=bool(e.get("interactive", False)),
                confidence=float(e.get("confidence", 0) or 0),
                source=ElementSource.VISION,
            )
        except (TypeError, ValueError):  # noqa: BLE001
            return None

    @staticmethod
    def _normalise_camera(data: Dict[str, Any], img_size: tuple) -> Dict[str, Any]:
        objects = []
        for i, o in enumerate(data.get("objects") or []):
            el = GemmaVision._element_from_dict(i, o)
            if el is not None and el.label:
                objects.append(el.to_dict())
        return {"summary": str(data.get("summary") or ""), "objects": objects, "raw": ""}


__all__ = ["DEFAULT_MODEL", "GemmaVision", "GemmaVisionError"]