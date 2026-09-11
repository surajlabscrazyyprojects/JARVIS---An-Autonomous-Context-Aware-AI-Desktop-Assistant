from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


class TaskScheduler:
    def __init__(self, task_store: Any, event_store: Any) -> None:
        self.task_store = task_store
        self.event_store = event_store
        self._queue: List[Dict[str, Any]] = []
        self._completed: Dict[str, bool] = {}
        self._retries: Dict[str, int] = {}

    def submit(self, task_id: str, priority: str = "normal", dependencies: Optional[List[str]] = None) -> None:
        p_val = 10 if priority == "voice" else (1 if priority == "background" else 5)
        self._queue.append({
            "task_id": task_id,
            "priority": priority,
            "priority_val": p_val,
            "dependencies": dependencies or [],
            "state": "QUEUED",
            "timestamp": time.time(),
        })
        self._queue.sort(key=lambda x: x["priority_val"], reverse=True)

    def acquire_next(self) -> Optional[str]:
        for item in self._queue:
            if item["state"] == "QUEUED":
                deps = item["dependencies"]
                if all(self._completed.get(d, False) for d in deps):
                    item["state"] = "RUNNING"
                    return item["task_id"]
        return None

    def complete(self, task_id: str, success: bool = True) -> None:
        self._completed[task_id] = success
        for item in self._queue:
            if item["task_id"] == task_id:
                item["state"] = "COMPLETED" if success else "FAILED"

    def retry(self, task_id: str, reason: str = "") -> int:
        cnt = self._retries.get(task_id, 0) + 1
        self._retries[task_id] = cnt
        for item in self._queue:
            if item["task_id"] == task_id:
                item["state"] = "QUEUED"
        return cnt

    def status(self) -> Dict[str, Any]:
        tasks_map = {item["task_id"]: item for item in self._queue}
        return {"tasks": tasks_map}
