from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SystemState:
    inference_mode: str = "normal"
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    disk_free_gb: float = 0.0
    battery_percent: Optional[float] = None


class DesktopObserver:
    def __init__(self) -> None:
        pass

    def get_system_state(self) -> SystemState:
        return SystemState()

    def get_active_window(self) -> str:
        try:
            import pygetwindow as gw
            w = gw.getActiveWindow()
            return w.title if w else ""
        except Exception:
            return ""

    def get_active_window_info(self) -> Dict[str, Any]:
        title = self.get_active_window()
        application = ""
        try:
            import pygetwindow as gw
            window = gw.getActiveWindow()
            if window and title:
                application = title.split(" - ")[-1].strip() or title
        except Exception:
            pass
        return {
            "title": title,
            "application": application,
            "timestamp": time.time(),
            "availability": "available" if title else "unavailable",
            "confidence": 0.9 if title else 0.0,
        }

    def observe(self) -> Dict[str, Any]:
        info = self.get_active_window_info()
        return {"active_window": info["title"], **info}
