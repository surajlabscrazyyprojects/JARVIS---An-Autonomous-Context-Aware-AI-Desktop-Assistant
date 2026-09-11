from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from jarvis.hud_launcher import is_hud_running

log = logging.getLogger("jarvis.autostart")


def verify_hud_started(proc: Optional[Any] = None) -> bool:
    return is_hud_running(proc)


class ActivationController:
    def __init__(self, wake_service: Any, launch_hud_fn: Optional[Callable[[], Any]] = None) -> None:
        self.wake_service = wake_service
        self.launch_hud_fn = launch_hud_fn
        self._active = False
        self._hud_proc: Optional[Any] = None

    def _backend_ready(self) -> bool:
        return True

    def _stop_owned_backend(self) -> None:
        pass

    def activate(self) -> bool:
        if self._active and is_hud_running(self._hud_proc):
            return True

        if not self.launch_hud_fn:
            return False

        # Attempt to launch
        proc = self.launch_hud_fn()
        if not proc:
            # Retry once
            proc = self.launch_hud_fn()
            if not proc:
                self._stop_owned_backend()
                return False

        self._hud_proc = proc
        started = verify_hud_started(proc)
        if not started:
            # Retry
            proc = self.launch_hud_fn()
            self._hud_proc = proc
            started = verify_hud_started(proc)
            if not started:
                self._stop_owned_backend()
                return False

        self._active = True
        return True
