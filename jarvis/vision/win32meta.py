"""
jarvis.vision.win32meta
=======================
Deterministic Level-1 window metadata from the Win32 API (ctypes only —
no extra dependencies). This is the cheapest observation: active window,
application, title, bounds, cursor and screen size.

Used by the analyzer for ObservationLevel.WINDOW_META and to seed the app
context for interpretation (spec section 28).
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from typing import Any, Dict, List, Optional

from jarvis.vision.contracts import Bounds, Point

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def screen_size() -> tuple:
    return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def cursor_position() -> Point:
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return Point(pt.x, pt.y)


def foreground_hwnd() -> int:
    return user32.GetForegroundWindow()


def window_title(hwnd: int) -> str:
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_rect(hwnd: int) -> Optional[Bounds]:
    if not hwnd:
        return None
    rect = ctypes.wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return Bounds(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def window_is_visible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))


def process_name_for_hwnd(hwnd: int) -> str:
    """Best-effort executable name for an HWND ('' when unavailable)."""
    try:
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ""
        try:
            bufsz = ctypes.wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(bufsz))
            if ok:
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # pragma: no cover - ctypes edge cases
        return ""
    return ""


def get_active_window_info() -> Dict[str, Any]:
    """Level-1 observation of the current foreground window."""
    hwnd = foreground_hwnd()
    bounds = window_rect(hwnd)
    return {
        "hwnd": hwnd,
        "title": window_title(hwnd),
        "bounds": bounds,
        "application": process_name_for_hwnd(hwnd),
        "visible": window_is_visible(hwnd),
        "cursor": cursor_position(),
        "screen_size": screen_size(),
    }


def list_window_titles(limit: int = 50) -> List[str]:
    """Enumerate visible top-level window titles (deterministic, ctypes)."""
    titles: List[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum_proc(hwnd, _lparam):  # pragma: no cover - exercised live
        if window_is_visible(hwnd):
            t = window_title(hwnd)
            if t and len(titles) < limit:
                titles.append(t)
        return True

    user32.EnumWindows(_enum_proc, 0)  # type: ignore[arg-type]
    return titles


__all__ = [
    "cursor_position",
    "foreground_hwnd",
    "get_active_window_info",
    "list_window_titles",
    "process_name_for_hwnd",
    "screen_size",
    "window_is_visible",
    "window_rect",
    "window_title",
]