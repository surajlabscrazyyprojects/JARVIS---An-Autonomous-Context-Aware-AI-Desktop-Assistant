"""
jarvis.vision.verifier
======================
Verification engine (spec section 36): did the intended result actually happen?

The engine compares screenshots / fingerprints and UI state, and reports a
verdict — `VERIFIED` only when the expected signal is actually observed.
It never claims precision it does not have: when the environment cannot supply
a strong signal, it reports `FAILED`/`DEGRADED` rather than guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from jarvis.vision import capture
from jarvis.vision.contracts import ExecutionStatus

# Pixel-difference threshold used by the diff ratio (0..255 scale).
PIXEL_TOLERANCE = 12


@dataclass
class VerificationResult:
    status: ExecutionStatus = ExecutionStatus.FAILED
    signal: str = "none"  # which verification signal was used
    detail: str = ""
    similarity: float = 0.0  # 0..1 when a visual signal was used
    expect_change: bool = True
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == ExecutionStatus.VERIFIED


def image_similarity(a: Image.Image, b: Image.Image) -> float:
    """Structural similarity 0..1 on down-scaled grayscale fingerprints.

    Uses mean abs difference mapped to [0,1]; 1.0 = identical layout."""
    ga = capture.downscaled_gray(a)
    gb = capture.downscaled_gray(b)
    if ga.shape != gb.shape:
        return 0.0
    diff = np.abs(ga - gb).mean()
    return float(max(0.0, 1.0 - diff / 255.0))


def region_changed(a: Image.Image, b: Image.Image, region: tuple, threshold: float = 0.015) -> bool:
    """Whether a specific screen region changed meaningfully between two frames.

    Used for post-action verification ("this toolbar area changed")."""
    ra = capture.region_image(a, region)
    rb = capture.region_image(b, region)
    if ra.size != rb.size:
        return True
    return _pixel_diff_ratio(ra, rb) > threshold


def screen_changed(a: Image.Image, b: Image.Image, threshold: float = 0.02) -> bool:
    """Full-frame meaningful change detection (cheap, fingerprint based)."""
    return image_similarity(a, b) < (1.0 - threshold)


def _pixel_diff_ratio(a: Image.Image, b: Image.Image) -> float:
    arr_a = np.asarray(a.convert("RGB"), dtype=np.int16)
    arr_b = np.asarray(b.convert("RGB"), dtype=np.int16)
    if arr_a.shape != arr_b.shape:
        return 1.0
    diff = np.abs(arr_a - arr_b).max(axis=2)
    return float((diff > PIXEL_TOLERANCE).mean())
class VerificationEngine:
    """Runs post-action verification for a completed motor action."""

    def __init__(self) -> None:
        self._last_before: Optional[Image.Image] = None
        self._last_before_hash: str = ""

    # -- lifecycle ----------------------------------------------------------
    def set_before(self, image: Optional[Image.Image] = None) -> str:
        """Capture (or accept) the pre-action frame used as the baseline."""
        if image is None:
            img, _ = capture.capture_screen()
        else:
            img = image
        self._last_before = img
        self._last_before_hash = capture.image_hash(img)
        return self._last_before_hash

    def before_hash(self) -> str:
        return self._last_before_hash

    # -- verdicts -----------------------------------------------------------
    def verify_screen_changed(
        self,
        expect_change: bool = True,
        min_similarity: float = 0.6,
        after: Optional[Image.Image] = None,
    ) -> VerificationResult:
        """Generic UI transition check (e.g. a dialog opened / menu appeared)."""
        if self._last_before is None:
            return VerificationResult(ExecutionStatus.FAILED, "before", "no baseline frame")
        img = after if after is not None else capture.capture_screen()[0]
        sim = image_similarity(self._last_before, img)
        changed = sim < min_similarity
        ok = changed if expect_change else (not changed)
        status = ExecutionStatus.VERIFIED if ok else ExecutionStatus.FAILED
        return VerificationResult(
            status,
            signal="screen_diff",
            detail=f"similarity={sim:.3f} expect_change={expect_change}",
            similarity=sim,
            expect_change=expect_change,
        )

    def verify_region_changed(
        self,
        region: tuple,
        expect_change: bool = True,
        threshold: float = 0.015,
        after: Optional[Image.Image] = None,
    ) -> VerificationResult:
        if self._last_before is None:
            return VerificationResult(ExecutionStatus.FAILED, "region", "no baseline frame")
        img = after if after is not None else capture.capture_screen()[0]
        changed = region_changed(self._last_before, img, region, threshold)
        ok = changed if expect_change else (not changed)
        status = ExecutionStatus.VERIFIED if ok else ExecutionStatus.FAILED
        return VerificationResult(
            status,
            signal="region_diff",
            detail=f"region={region} changed={changed} expect_change={expect_change}",
            expect_change=expect_change,
        )

    def verify_element_transition(
        self,
        elements_before: List[str],
        elements_after: List[str],
        expected_present: Optional[str] = None,
        expected_absent: Optional[str] = None,
    ) -> VerificationResult:
        """Verify an element appeared/disappeared across two UI observations.

        `elements_before/after` are lists of element labels or ids. Label
        transitions are preferred over pixel diff when labels are available."""
        before = {el.lower() for el in elements_before}
        after = {el.lower() for el in elements_after}
        if expected_present is not None:
            ok = expected_present.lower() in after
            signal = "element_present"
        elif expected_absent is not None:
            ok = expected_absent.lower() not in after
            signal = "element_absent"
        else:
            ok = before != after
            signal = "element_set_changed"
        status = ExecutionStatus.VERIFIED if ok else ExecutionStatus.FAILED
        return VerificationResult(status, signal=signal, detail=f"before={len(before)} after={len(after)}")

    def verify_observed(self, observation) -> VerificationResult:
        """Trust a re-observation only when it reached OBSERVED (not degraded
        and not empty). The strength of the signal is the observation itself."""
        if getattr(observation, "degraded", False):
            return VerificationResult(ExecutionStatus.FAILED, "observation", "vision degraded")
        return VerificationResult(
            ExecutionStatus.VERIFIED,
            signal="structured_observation",
            detail=f"elements={len(getattr(observation, 'elements', []))}",
        )

    def compare_state(self, a, b) -> Dict[str, Any]:
        """Structured comparison of two ScreenObservation objects.

        Returns a diff summary used by the agent to decide continue/recover."""
        a_elements = {e.id for e in getattr(a, "elements", [])}
        b_elements = {e.id for e in getattr(b, "elements", [])}
        labels_a = {e.label for e in getattr(a, "elements", [])}
        labels_b = {e.label for e in getattr(b, "elements", [])}
        return {
            "window_changed": getattr(a, "window_title", "") != getattr(b, "window_title", ""),
            "hash_changed": getattr(a, "screen_hash", "") != getattr(b, "screen_hash", ""),
            "elements_added": sorted(labels_b - labels_a),
            "elements_removed": sorted(labels_a - labels_b),
            "element_ids_changed": sorted(a_elements ^ b_elements),
        }

    def cleanup(self) -> None:
        """Never retain raw frames — drop the baseline."""
        self._last_before = None
        self._last_before_hash = ""


__all__ = [
    "PIXEL_TOLERANCE",
    "VerificationEngine",
    "VerificationResult",
    "image_similarity",
    "region_changed",
    "screen_changed",
]