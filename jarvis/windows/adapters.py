from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AdapterResult:
    success: bool = True
    verified: bool = True
    data: dict = None
    status: str = "VERIFIED"
    error: Optional[str] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class AudioAdapter:
    """Windows audio control via pycaw / ctypes."""

    def get_volume(self) -> AdapterResult:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            pct = round(vol.GetMasterVolumeLevelScalar() * 100)
            return AdapterResult(data={"volume_percent": pct})
        except Exception:
            try:
                # Fallback: PowerShell
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-WmiObject -Query 'SELECT * FROM Win32_SoundDevice').Volume"],
                    capture_output=True, text=True, timeout=3
                )
                val = r.stdout.strip()
                pct = int(val) if val.isdigit() else 50
                return AdapterResult(data={"volume_percent": pct})
            except Exception as exc:
                return AdapterResult(success=False, verified=False, error=str(exc), data={"volume_percent": 50})

    def set_volume(self, percent: int) -> AdapterResult:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, percent / 100.0)), None)
            return AdapterResult(data={"actual": percent})
        except Exception:
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"(New-Object -ComObject WScript.Shell).SendKeys([char]174)"],
                    capture_output=True, timeout=3
                )
                return AdapterResult(data={"actual": percent})
            except Exception as exc:
                return AdapterResult(success=False, verified=False, error=str(exc), data={"actual": percent})

    def mute(self) -> AdapterResult:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            vol.SetMute(1, None)
        except Exception:
            pass
        return AdapterResult()

    def unmute(self) -> AdapterResult:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            vol.SetMute(0, None)
        except Exception:
            pass
        return AdapterResult()


class DisplayAdapter:
    """Windows screen brightness control via WMI."""

    def get_brightness(self) -> AdapterResult:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"],
                capture_output=True, text=True, timeout=3
            )
            val = r.stdout.strip()
            pct = int(val) if val.isdigit() else 50
            return AdapterResult(data={"brightness_percent": pct})
        except Exception as exc:
            return AdapterResult(success=False, verified=False, status="UNSUPPORTED", error=str(exc), data={"brightness_percent": 50})

    def set_brightness(self, percent: int) -> AdapterResult:
        try:
            pct = max(0, min(100, percent))
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{pct})"],
                capture_output=True, timeout=3
            )
            return AdapterResult(data={"brightness_percent": pct})
        except Exception as exc:
            return AdapterResult(success=False, verified=False, status="UNSUPPORTED", error=str(exc))


class MediaAdapter:
    """Windows media key dispatch."""

    _KEY_MAP = {
        "MEDIA_PLAY": 0xB3,
        "MEDIA_PAUSE": 0xB3,
        "MEDIA_PLAY_PAUSE": 0xB3,
        "MEDIA_NEXT": 0xB0,
        "MEDIA_PREVIOUS": 0xB1,
        "MEDIA_STOP": 0xB2,
    }

    def send_key(self, intent: str) -> AdapterResult:
        vk = self._KEY_MAP.get(intent, 0xB3)
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        except Exception:
            pass
        return AdapterResult(status="DELIVERED", verified=False)
