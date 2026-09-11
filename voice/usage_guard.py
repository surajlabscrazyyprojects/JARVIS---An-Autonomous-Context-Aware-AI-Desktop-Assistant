"""Conservative local usage guards for Fish Audio (§14).

Even though s2.1-pro-free is a free dev model, we bound our own usage so a
runaway loop can never burn quota, spam the API, or grow state unboundedly.
When a limit trips: no Fish call is made; the caller falls back (local or
text-only) and records a clear internal status. Never a paid model.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class UsageGuardTripped(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class UsageGuard:
    def __init__(self, max_requests_per_minute: int = 20,
                 max_utf8_bytes_per_session: int = 200_000,
                 max_response_chars: int = 2_000,
                 max_concurrent_streams: int = 1):
        self.max_rpm = max(1, int(max_requests_per_minute))
        self.max_bytes = max(1, int(max_utf8_bytes_per_session))
        self.max_chars = max(1, int(max_response_chars))
        self.max_streams = max(1, int(max_concurrent_streams))
        self._lock = threading.Lock()
        self._req_times: deque = deque()
        self._bytes_used = 0
        self._active_streams = 0
        self.trips = 0

    def _prune(self, now: float):
        while self._req_times and self._req_times[0] <= now - 60.0:
            self._req_times.popleft()

    def check_request(self, text: str) -> None:
        """Reserve one request; raise UsageGuardTripped on any limit."""
        n_bytes = len((text or "").encode("utf-8"))
        if len(text or "") > self.max_chars:
            raise UsageGuardTripped(
                f"response too long ({len(text)} chars > {self.max_chars}) — shortened or text-only")
        now = time.time()
        with self._lock:
            self._prune(now)
            if len(self._req_times) >= self.max_rpm:
                self.trips += 1
                raise UsageGuardTripped(
                    f"rate limit ({self.max_rpm}/min) — backing off, text-only for now")
            if self._bytes_used + n_bytes > self.max_bytes:
                self.trips += 1
                raise UsageGuardTripped("session byte budget exhausted — text-only for now")
            self._req_times.append(now)
            self._bytes_used += n_bytes

    def acquire_stream(self):
        """Context manager for one synthesis stream slot."""
        return _StreamSlot(self)

    def stats(self) -> dict:
        with self._lock:
            self._prune(time.time())
            return {
                "rpm_used": len(self._req_times),
                "rpm_max": self.max_rpm,
                "bytes_used": self._bytes_used,
                "bytes_max": self.max_bytes,
                "active_streams": self._active_streams,
                "trips": self.trips,
            }


class _StreamSlot:
    def __init__(self, guard: UsageGuard):
        self._g = guard

    def __enter__(self):
        with self._g._lock:
            if self._g._active_streams >= self._g.max_streams:
                self._g.trips += 1
                raise UsageGuardTripped("another synthesis is already running")
            self._g._active_streams += 1
        return self

    def __exit__(self, *exc):
        with self._g._lock:
            self._g._active_streams = max(0, self._g._active_streams - 1)
        return False
