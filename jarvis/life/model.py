from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Optional


@dataclass
class RoutineBlock:
    id: str
    title: str
    start: str
    end: str
    category: str
    subject: str = ""
    monitor_distractions: bool = False
    entertainment_allowed: bool = False
    reminder: Dict[str, Any] = field(default_factory=dict)

    @property
    def start_minutes(self):
        return _minutes(self.start)

    @property
    def end_minutes(self):
        return _minutes(self.end)


def _minutes(value: str) -> int:
    h, m = (int(x) for x in value.split(":"))
    return h * 60 + m


def block_covers(block: RoutineBlock, minute: int) -> bool:
    start, end = block.start_minutes, block.end_minutes
    if start == end:
        return True
    return start <= minute < end if start < end else minute >= start or minute < end


@dataclass
class FocusState:
    mode: str
    subject: str = ""
    remaining_seconds: int = 0
    block_id: str = ""


@dataclass
class WindowObservation:
    app: str = ""
    title: str = ""
    url: str = ""

