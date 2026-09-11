"""
SpeechQueue - prioritized, cancellable, serial speech queue.

A single worker drains the queue: it synthesizes OFF the caller thread and
hands audio to the AudioPlaybackManager. Higher-priority items jump the line;
items can be cancelled by id (used for barge-in / interruption).
"""
from __future__ import annotations

import heapq
import threading
import time
import uuid

from .log import logger

_PRIORITY = {"low": 0, "normal": 1, "high": 2, "critical": 3}


class SpeechQueue:
    def __init__(self):
        self._counter = 0
        self._heap = []
        self._items = {}
        self._cancelled = set()
        self._lock = threading.Lock()
        self._current = None

    def enqueue(self, text: str, emotion=None, priority: str = "normal",
                meta: dict | None = None) -> str:
        item_id = str(uuid.uuid4())
        prio = _PRIORITY.get(priority, 1)
        with self._lock:
            self._counter += 1
            item = {
                "id": item_id, "text": text, "emotion": emotion,
                "priority": prio, "seq": self._counter, "meta": meta or {},
                "enqueued": time.time(),
            }
            self._items[item_id] = item
            heapq.heappush(self._heap, (-prio, self._counter, item_id))
        return item_id

    def cancel(self, item_id: str):
        with self._lock:
            self._cancelled.add(item_id)
            self._items.pop(item_id, None)

    def cancel_all(self):
        with self._lock:
            for iid in list(self._items.keys()):
                self._cancelled.add(iid)
            self._items.clear()
            self._heap.clear()

    def pop(self):
        with self._lock:
            while self._heap:
                neg_prio, seq, iid = heapq.heappop(self._heap)
                if iid in self._cancelled:
                    self._cancelled.discard(iid)
                    continue
                item = self._items.pop(iid, None)
                if item is None:
                    continue
                self._current = iid
                return item
            self._current = None
            return None

    def is_cancelled(self, item_id: str) -> bool:
        with self._lock:
            return item_id in self._cancelled

    def mark_done(self, item_id: str):
        with self._lock:
            if self._current == item_id:
                self._current = None

    @property
    def current(self):
        return self._current

    def pending(self) -> int:
        with self._lock:
            return len(self._heap)
