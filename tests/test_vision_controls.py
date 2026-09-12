from PIL import Image

from jarvis.vision.analyzer import VisionAnalyzer
from jarvis.vision.coordinates import CoordinateTransform
from jarvis.vision.ocr import OCRManager
from jarvis.vision.privacy import VisionMode, VisionPrivacy


def test_coordinate_transform_handles_scaling_and_monitor_offset():
    t = CoordinateTransform(1000, 500, desktop_x=-1920, desktop_y=20, desktop_width=2000, desktop_height=1000)
    assert t.vision_to_desktop(500, 250) == (-920, 520)
    assert t.desktop_to_vision(-920, 520) == (500, 250)


def test_privacy_off_prevents_capture(monkeypatch):
    privacy = VisionPrivacy()
    privacy.set_mode(VisionMode.OFF)
    analyzer = VisionAnalyzer(privacy=privacy)
    monkeypatch.setattr("jarvis.vision.analyzer.win32meta.get_active_window_info", lambda: (_ for _ in ()).throw(AssertionError("captured")))
    obs = analyzer.analyze_screen(goal="what is on my screen")
    assert obs.summary == "SCREEN_VISION_DISABLED"
    assert obs.degraded is True


def test_ocr_is_explicitly_degraded_when_backend_missing(monkeypatch):
    ocr = OCRManager()
    monkeypatch.setattr(ocr, "_load", lambda: None)
    result = ocr.extract(Image.new("RGB", (4, 4)))
    assert result["ok"] is False
