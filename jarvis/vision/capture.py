"""
jarvis.vision.capture
=====================
Screen/region capture + perceptual hashing + model-ready encoding.

Everything here is dependency-light: we use PIL.ImageGrab (Windows) for
capture and numpy (already in the venv) for the difference hash used by the
screen-change detector (spec section 23). Raw frames are never stored for
long: we keep only compact hashes and tiny down-sampled fingerprints.
"""
from __future__ import annotations

import base64
import hashlib
import io
import time
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageGrab

DEFAULT_MAX_ANALYSIS_DIM = 1280  # longest edge sent to Gemma (perf: section 39)
DEFAULT_HASH_SIZE = 32  # dHash grid 32x32 -> 1024-bit fingerprint


def capture_screen(region: Optional[Tuple[int, int, int, int]] = None) -> Tuple[Image.Image, int]:
    """Capture the full screen (or an (x, y, w, h) region).

    Returns (PIL.Image, capture_ms)."""
    t0 = time.perf_counter()
    if region:
        img = ImageGrab.grab(bbox=region, all_screens=True)
    else:
        img = ImageGrab.grab(all_screens=True)
    ms = int((time.perf_counter() - t0) * 1000)
    return img, ms


def list_monitors() -> list[dict]:
    """Return monitor geometry when the optional Windows enumerator exists."""
    try:
        from screeninfo import get_monitors  # type: ignore
        return [{"id": i, "x": int(m.x), "y": int(m.y), "width": int(m.width), "height": int(m.height),
                 "scale": 1.0, "name": getattr(m, "name", "")} for i, m in enumerate(get_monitors())]
    except Exception:
        img, _ = capture_screen()
        return [{"id": 0, "x": 0, "y": 0, "width": img.width, "height": img.height, "scale": 1.0, "name": "primary"}]


def capture_monitor(monitor_id: int = 0) -> Tuple[Image.Image, int]:
    monitors = list_monitors()
    if monitor_id < 0 or monitor_id >= len(monitors):
        raise ValueError(f"unknown monitor id: {monitor_id}")
    m = monitors[monitor_id]
    return capture_screen((m["x"], m["y"], m["width"], m["height"]))


def capture_active_window() -> Tuple[Image.Image, int]:
    """Capture only the foreground window, excluding unrelated monitors."""
    from jarvis.vision import win32meta
    bounds = win32meta.window_rect(win32meta.foreground_hwnd())
    if bounds is None or bounds.width <= 0 or bounds.height <= 0:
        return capture_screen()
    return capture_screen(bounds.to_region())


def image_hash(img: Image.Image, size: int = DEFAULT_HASH_SIZE) -> str:
    """Perceptual difference-hash (robust to subtle encode noise, sensitive to
    real layout/content change). Used for screen-change detection plus a
    stable element of the visual-memory key."""
    arr = _to_gray_array(img, size)
    diff = (arr[:, 1:] > arr[:, :-1]).astype(np.uint8)
    bits = np.packbits(diff)
    return hashlib.md5(bits.tobytes()).hexdigest()


def image_pixel_hash(img: Image.Image) -> str:
    """Trivial bit-exact hash used only for cache bookkeeping (not change
    detection)."""
    return hashlib.md5(img.tobytes()).hexdigest()


def _to_gray_array(img: Image.Image, size: int) -> np.ndarray:
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    return np.asarray(g, dtype=np.uint8)


def downscaled_gray(img: Image.Image, size: int = 64) -> np.ndarray:
    """Compact grayscale fingerprint used by the verification engine."""
    return np.asarray(img.convert("L").resize((size, size), Image.LANCZOS), dtype=np.float32)


def resize_to_max(img: Image.Image, max_dim: int = DEFAULT_MAX_ANALYSIS_DIM) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_dim:
        return img
    ratio = max_dim / float(longest)
    return img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)


def encode_jpeg_base64(img: Image.Image, quality: int = 80, max_dim: int = DEFAULT_MAX_ANALYSIS_DIM) -> str:
    """Return a data-URL-safe JPEG base64 payload for the vision model."""
    resized = resize_to_max(img, max_dim)
    buf = io.BytesIO()
    if resized.mode in ("RGBA", "P", "LA"):
        resized = resized.convert("RGB")
    resized.save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def capture_screen_hash(region: Optional[Tuple[int, int, int, int]] = None) -> Tuple[str, int]:
    """Capture + hash in one call (returns (hash, capture_ms))."""
    img, ms = capture_screen(region)
    return image_hash(img), ms


def region_image(img: Image.Image, region: Tuple[int, int, int, int]) -> Image.Image:
    """Crop an observation image to an (x, y, w, h) region (screen coords)."""
    return img.crop((region[0], region[1], region[0] + region[2], region[1] + region[3]))


def clamp_region(region: Tuple[int, int, int, int], img_w: int, img_h: int) -> Optional[Tuple[int, int, int, int]]:
    x, y, w, h = (int(v) for v in region)
    if w <= 0 or h <= 0:
        return None
    x = max(0, min(img_w - 1, x))
    y = max(0, min(img_h - 1, y))
    w = max(1, min(w, img_w - x))
    h = max(1, min(h, img_h - y))
    return (x, y, w, h)


__all__ = [
    "DEFAULT_HASH_SIZE",
    "DEFAULT_MAX_ANALYSIS_DIM",
    "capture_screen",
    "capture_active_window",
    "capture_monitor",
    "list_monitors",
    "capture_screen_hash",
    "clamp_region",
    "downscaled_gray",
    "encode_jpeg_base64",
    "image_hash",
    "image_pixel_hash",
    "region_image",
    "resize_to_max",
]
