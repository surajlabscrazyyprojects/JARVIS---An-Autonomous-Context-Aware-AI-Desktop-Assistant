"""
jarvis.vision.camera
====================
Camera vision context — completely separate from the screen context
(spec sections 29-33). Never send camera observations to a screen-control
action and never assume a screen object and camera object share a source.

The analysis runs on demand (explicitly enabled -> required frame sampling ->
analysis -> result). Adaptive frame rate: if a frame has not meaningfully
changed, the caller can skip expensive inference via ``should_analyze``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from jarvis.vision import capture
from jarvis.vision.contracts import CameraObservation, ContextType, ExecutionStatus
from jarvis.vision.gemma import GemmaVision

CAMERA_SAMPLE_MIN_CHANGE = 0.985  # frames more similar than this are "same scene"


class CameraVision:
    """Handles camera frame analysis + lightweight tracking (no heavy per-frame
    model inference — model detections are spaced out).

    Accepts either a PIL.Image or a raw 3D numpy frame (must be converted to
    PIL by the caller to avoid pulling in an image-io dependency here)."""

    def __init__(
        self,
        gemma: Optional[GemmaVision] = None,
        adaptive: bool = True,
        min_interval_s: float = 1.5,
    ) -> None:
        self.gemma = gemma or GemmaVision()
        self.adaptive = adaptive
        self.min_interval_s = min_interval_s
        self._last_observation: Optional[CameraObservation] = None
        self._last_frame_hash: str = ""
        self._last_analyzed_ts: float = 0.0
        self._frame_index: int = 0

    # -- separation guard ---------------------------------------------------
    @property
    def context(self) -> ContextType:
        return ContextType.CAMERA

    def should_analyze(self, frame) -> bool:
        """Adaptive frame-rate sampling: skip when scene did not change, when
        the last inference is recent, or when tracking can bridge the gap."""
        try:
            img = _frame_to_pil(frame)
        except TypeError:
            return True
        h = capture.image_hash(img)
        same_scene = bool(self._last_frame_hash) and (h == self._last_frame_hash)
        import time

        recent = (time.time() - self._last_analyzed_ts) < self.min_interval_s
        if self.adaptive and (same_scene or recent):
            self._last_frame_hash = h
            return False
        self._last_frame_hash = h
        return True

    def analyze_frame(self, frame, goal: str = "") -> CameraObservation:
        """Analyze one camera frame (blocking; caller controls rate)."""
        img = _frame_to_pil(frame)
        h = capture.image_hash(img)
        self._frame_index += 1
        import time

        t0 = time.perf_counter()
        if not self.gemma.is_available():
            obs = CameraObservation(
                status=ExecutionStatus.FAILED,
                scene_hash=h,
                frame_index=self._frame_index,
                degraded=True,
                summary="VISION_DEGRADED - camera analysis unavailable",
            )
        else:
            try:
                data = self.gemma.analyze_camera(img, goal)
                objects = _objects_from_dict(data.get("objects", []))
                obs = CameraObservation(
                    status=ExecutionStatus.OBSERVED,
                    scene_hash=h,
                    summary=data.get("summary", ""),
                    objects=objects,
                    frame_index=self._frame_index,
                    confidence=min(1.0, 0.1 + 0.05 * len(objects)),
                    inference_ms=int((time.perf_counter() - t0) * 1000),
                    meta={"goal": goal},
                )
            except Exception as exc:  # noqa: BLE001
                obs = CameraObservation(
                    status=ExecutionStatus.FAILED,
                    scene_hash=h,
                    frame_index=self._frame_index,
                    degraded=True,
                    summary=f"VISION_DEGRADED - {exc}",
                )
        self._last_observation = obs
        import time as _t

        self._last_analyzed_ts = _t.time()
        return obs

    def track(self, observations: List[CameraObservation]) -> Dict[str, Any]:
        """Lightweight association tracker between model detections: nearest
        center match within a radius. Revalidation happens periodically via
        analyze_frame (spec section 31)."""
        tracks: Dict[str, Dict[str, Any]] = {}
        for obs in observations:
            for obj in obs.objects:
                c = obj.center
                best_key = None
                best_dist = float("inf")
                for key, t in tracks.items():
                    lx = t.get("last_x", 0)
                    ly = t.get("last_y", 0)
                    d = (lx - c.x) ** 2 + (ly - c.y) ** 2
                    if d < best_dist and d < 2500:  # 50px radius
                        best_key, best_dist = key, d
                key = best_key or f"obj_{len(tracks)}"
                tracks[key] = {"last_x": c.x, "last_y": c.y, "label": obj.label, "seen": obs.frame_index}
        return tracks


def _frame_to_pil(frame):
    """Accept PIL.Image or numpy RGB array; raise TypeError otherwise."""
    if hasattr(frame, "convert"):
        return frame
    raise TypeError("camera frame must be PIL.Image (convert numpy frames before calling)")


def _objects_from_dict(data: List[Dict[str, Any]]):
    from jarvis.vision.contracts import ElementType, Point, VisionElement

    from jarvis.vision.gemma import GemmaVision

    out = []
    for i, o in enumerate(data):
        el = GemmaVision._element_from_dict(i, o)
        if el is not None and el.label:
            el.type = ElementType.OBJECT
            out.append(el)
    return out


__all__ = ["CAMERA_SAMPLE_MIN_CHANGE", "CameraVision"]