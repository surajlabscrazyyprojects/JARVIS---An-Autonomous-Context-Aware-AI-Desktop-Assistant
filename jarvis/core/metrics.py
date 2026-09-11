from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict


class Metrics:
    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}

    def record(self, category: str, duration_ms: float, tokens: int = 0) -> None:
        if category not in self._data:
            self._data[category] = {"count": 0, "total_ms": 0.0, "total_tokens": 0}
        rec = self._data[category]
        rec["count"] += 1
        rec["total_ms"] += duration_ms
        rec["total_tokens"] += tokens

    @contextmanager
    def timed(self, category: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            ms = (time.perf_counter() - t0) * 1000.0
            self.record(category, ms)

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        snap = {}
        for k, v in self._data.items():
            cnt = v["count"]
            avg = v["total_ms"] / cnt if cnt > 0 else 0.0
            snap[k] = {
                "count": cnt,
                "total_ms": v["total_ms"],
                "avg_ms": avg,
                "total_tokens": v["total_tokens"],
            }
        return snap
