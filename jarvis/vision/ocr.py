"""Optional local OCR adapter.

OCR is deliberately local and lazy.  If Tesseract/pytesseract is absent the
adapter reports an explicit degraded result instead of silently using a cloud
provider or inventing text.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class OCRManager:
    def __init__(self) -> None:
        self._engine = None
        self._error: Optional[str] = None

    def _load(self):
        if self._engine is not None or self._error is not None:
            return self._engine
        try:
            import pytesseract  # type: ignore
            self._engine = pytesseract
        except Exception as exc:  # pragma: no cover - environment dependent
            self._error = str(exc)
        return self._engine

    @property
    def available(self) -> bool:
        return self._load() is not None

    def extract(self, image) -> Dict[str, Any]:
        engine = self._load()
        if engine is None:
            return {"ok": False, "text": "", "items": [], "error": f"local OCR unavailable: {self._error}"}
        try:
            data = engine.image_to_data(image, output_type=engine.Output.DICT)
            items: List[Dict[str, Any]] = []
            words: List[str] = []
            for i, raw in enumerate(data.get("text", [])):
                text = str(raw or "").strip()
                if not text:
                    continue
                words.append(text)
                items.append({
                    "text": text,
                    "bbox": [int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i])],
                    "confidence": max(0.0, float(data["conf"][i]) / 100.0),
                })
            return {"ok": True, "text": " ".join(words), "items": items}
        except Exception as exc:  # pragma: no cover - engine dependent
            return {"ok": False, "text": "", "items": [], "error": f"OCR failed: {exc}"}


__all__ = ["OCRManager"]
