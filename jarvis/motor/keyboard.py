"""
jarvis.motor.keyboard
=====================
Structured keyboard motor controller (spec sections 15-16).

Supports key press/down, key release/up, taps, hotkeys, sequences and text
input with structured key events. Every key currently held is tracked by the
input safety watchdog so combinations can never remain stuck — e.g. for
SHIFT+click or CTRL+multi-click coordination (section 16).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

import pyautogui

from jarvis.motor.watchdog import InputSafetyWatchdog
from jarvis.vision.contracts import ExecutionStatus


def _norm_key(name: str) -> str:
    k = (name or "").strip().lower()
    aliases = {"ctrl": "ctrl", "control": "ctrl", "cmd": "win", "command": "win",
               "return": "enter", "esc": "esc", "del": "delete", "shift": "shift"}
    return aliases.get(k, k)


def release_key_named(name: str) -> None:
    """Physical release used by the watchdog for emergency cleanup."""
    try:
        pyautogui.keyUp(_norm_key(name))
    except Exception:  # noqa: BLE001
        pass


def press_key_named(name: str) -> None:
    pyautogui.keyDown(_norm_key(name))


class KeyboardController:
    def __init__(self, watchdog: Optional[InputSafetyWatchdog] = None) -> None:
        self.watchdog = watchdog or InputSafetyWatchdog()

    @staticmethod
    def _result(ok: bool, status: ExecutionStatus, summary: str, **data: Any) -> Dict[str, Any]:
        return {"ok": ok, "status": status.value, "summary": summary, "data": data}

    # -- structured key events -------------------------------------------------
    def press(self, key: str) -> Dict[str, Any]:
        """Key DOWN only (stays held until release()). Tracked by watchdog."""
        key = _norm_key(key)
        try:
            pyautogui.keyDown(key)
            self.watchdog.press("keyboard", key)
            return self._result(True, ExecutionStatus.EXECUTING, f"key down: {key}")
        except Exception as exc:  # noqa: BLE001
            return self._result(False, ExecutionStatus.FAILED, f"keyDown failed: {exc}")

    def release(self, key: Optional[str] = None) -> Dict[str, Any]:
        """Key UP. With no key, release every tracked key (idempotent)."""
        if key is None:
            held = list(self.watchdog.held_keys())
            for k in held:
                release_key_named(k)
                self.watchdog.release("keyboard", k)
            return self._result(True, ExecutionStatus.OBSERVED, "released held keys", released=held)
        key = _norm_key(key)
        release_key_named(key)
        self.watchdog.release("keyboard", key)
        return self._result(True, ExecutionStatus.OBSERVED, f"key up: {key}")

    def tap(self, key: str, count: int = 1, interval: float = 0.05) -> Dict[str, Any]:
        key = _norm_key(key)
        try:
            pyautogui.press(key, presses=int(count), interval=interval)
            return self._result(True, ExecutionStatus.OBSERVED, f"pressed {key} x{count}")
        except Exception as exc:  # noqa: BLE001
            return self._result(False, ExecutionStatus.FAILED, f"press failed: {exc}")

    def hotkey(self, *keys: str) -> Dict[str, Any]:
        keys = [_norm_key(k) for k in keys]
        if not keys:
            return self._result(False, ExecutionStatus.FAILED, "no keys for hotkey")
        try:
            # Down in order, up in reverse; each held key tracked so an abort
            # mid-sequence can never leave a modifier stuck.
            for k in keys:
                pyautogui.keyDown(k)
                self.watchdog.press("keyboard", k)
            for k in reversed(keys):
                pyautogui.keyUp(k)
                self.watchdog.release("keyboard", k)
            return self._result(True, ExecutionStatus.OBSERVED, f"hotkey {'+'.join(keys)}")
        except Exception as exc:  # noqa: BLE001
            self.watchdog.release_all()
            return self._result(False, ExecutionStatus.FAILED, f"hotkey failed: {exc}")

    def type(self, text: str, interval: float = 0.02) -> Dict[str, Any]:
        if not text:
            return self._result(False, ExecutionStatus.FAILED, "empty text")
        try:
            pyautogui.typewrite(text, interval=interval)
            return self._result(True, ExecutionStatus.OBSERVED, f"typed {len(text)} chars")
        except Exception as exc:  # noqa: BLE001
            return self._result(False, ExecutionStatus.FAILED, f"type failed: {exc}")

    def sequence(self, keys: Sequence[str], interval: float = 0.02) -> Dict[str, Any]:
        """Type a string, or treat entries in brackets as hotkeys, e.g.
        ["hello", "[ctrl+s]"]. Simple deterministic sequence helper."""
        for entry in keys:
            entry = str(entry or "")
            if entry.startswith("[") and entry.endswith("]"):
                combo = entry[1:-1].split("+")
                r = self.hotkey(*combo)
                if not r.get("ok"):
                    return r
            else:
                r = self.type(entry, interval=interval)
                if not r.get("ok"):
                    return r
        return self._result(True, ExecutionStatus.OBSERVED, f"sequence of {len(keys)} inputs")

    # -- coordination ----------------------------------------------------------
    def release_all(self, include_mouse: bool = False) -> Dict[str, Any]:
        """Release all held keys (and optionally mouse buttons)."""
        self.watchdog.release_all()
        return self._result(True, ExecutionStatus.OBSERVED, "all held keys released")

    @property
    def held_keys(self) -> List[str]:
        return self.watchdog.held_keys()


__all__ = ["KeyboardController", "press_key_named", "release_key_named"]