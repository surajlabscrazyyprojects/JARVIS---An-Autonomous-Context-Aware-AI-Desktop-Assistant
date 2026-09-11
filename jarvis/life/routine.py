from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import json

from .model import FocusState, RoutineBlock, WindowObservation, block_covers

class DailyDay(dict):
    def __init__(self, value, day):
        super().__init__(value)
        self.date = day


def _default_blocks():
    raw = [
        ("wake", "Wake", "04:45", "05:15", "wake"),
        ("wash", "Morning preparation", "05:15", "05:30", "routine"),
        ("pooja", "Pooja", "05:30", "06:00", "pooja"),
        ("exercise", "Exercise", "06:00", "06:30", "health"),
        ("breakfast_prep", "Breakfast preparation", "06:30", "07:00", "meal"),
        ("chemistry_deep_study", "Chemistry Deep Study", "07:00", "09:30", "study"),
        ("breakfast", "Breakfast", "09:30", "10:00", "meal"),
        ("mathematics_deep_study", "Mathematics Deep Study", "10:00", "12:00", "study"),
        ("lunch", "Lunch", "12:00", "12:35", "meal"),
        ("rest", "Rest", "12:35", "13:00", "break"),
        ("physics_deep_study", "Physics Deep Study", "13:00", "15:00", "study"),
        ("break", "Break", "15:00", "15:30", "break"),
        ("snack", "Snack", "15:30", "16:00", "meal"),
        ("revision", "Revision", "16:00", "17:30", "study"),
        ("free_time", "Free time", "17:30", "18:00", "break"),
        ("evening_walk", "Evening walk", "18:00", "18:30", "health"),
        ("dinner", "Dinner", "18:30", "19:00", "meal"),
        ("practice", "Practice problems", "19:00", "20:00", "study"),
        ("planning", "Plan tomorrow", "20:00", "20:30", "routine"),
        ("relax", "Relaxation", "20:30", "21:00", "break"),
        ("prepare_sleep", "Prepare for sleep", "21:00", "22:00", "routine"),
        ("sleep", "Sleep", "22:00", "04:45", "sleep"),
        ("buffer", "Morning buffer", "04:45", "04:45", "routine"),
        ("daily_review", "Daily review", "21:00", "21:00", "routine"),
    ]
    blocks = []
    for ident, title, start, end, category in raw:
        study = category == "study"
        blocks.append(RoutineBlock(ident, title, start, end, category,
                                   subject=ident.split("_")[0] if study else "",
                                   monitor_distractions=study,
                                   entertainment_allowed=category in ("break", "free"),
                                   reminder={"enabled": True, "pre_start_minutes": 5,
                                             "end_wrapup_minutes": 5} if study else {}))
    return blocks


class RoutineManager:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.routine = _default_blocks()

    def blocks(self): return list(self.routine)
    def block_by_id(self, ident): return next(b for b in self.routine if b.id == ident)
    def replace_blocks(self, blocks):
        self.routine[:] = [b if isinstance(b, RoutineBlock) else RoutineBlock(**b) for b in blocks]


class ScheduleEngine:
    def __init__(self, routine): self.routine = routine

    def block_at(self, when: datetime):
        minute = when.hour * 60 + when.minute
        for block in self.routine:
            if block_covers(block, minute):
                return block
        return self.routine[-1]

    def next_block_after(self, when: datetime):
        current = self.block_at(when)
        if current.category == "sleep":
            return next((b for b in self.routine if b.id == "wake"), next(b for b in self.routine if b.category != "sleep"))
        blocks = self.routine
        index = blocks.index(current)
        if current.start_minutes == when.hour * 60 + when.minute:
            return current
        return blocks[(index + 1) % len(blocks)]


class DailyStateManager:
    def __init__(self, directory: Path):
        self.path = Path(directory) / "life_daily.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def _key(self, day): return str(day)
    def day(self, day):
        key = self._key(day)
        value = self.data.setdefault(key, {"fired": [], "completed": [], "hydration": 0,
                                         "last_hydration": None, "overrides": [], "exceptions": 0})
        if not isinstance(value, DailyDay):
            value = DailyDay(value, day)
            self.data[key] = value
        return value
    def _save(self): self.path.write_text(json.dumps(self.data, indent=2))
    def mark_fired(self, day, key):
        if key not in self.day(day)["fired"]: self.day(day)["fired"].append(key); self._save()
    def record_hydration_ack(self, day, when):
        d = self.day(day); d["hydration"] += 1; d["last_hydration"] = when.isoformat(); self._save()
    def add_override(self, day, override):
        self.day(day)["overrides"].append(override); self._save()
    def day_summary(self, day): return {"completed": self.day(day)["completed"]}


class Reminder:
    def __init__(self, key, kind, text, block=None):
        self.key, self.kind, self.text, self.block = key, kind, text, block


class ReminderEngine:
    def __init__(self, schedule, daily, config=None):
        self.schedule, self.daily = schedule, daily
        self.hydration_cfg = {"enabled": True, "interval_minutes": 30, "quiet_during_sleep": True,
                              "quiet_during_pooja": True, "quiet_during_meals": True,
                              "quiet_minutes_after_ack": 60}
        self.config = config or {}
        self.hydration_cfg.update(self.config.get("hydration", {}))
        self.config.setdefault("reminders", {}).setdefault("pre_start_minutes", 5)
        self.config["reminders"].setdefault("end_wrapup_minutes", 5)

    def due(self, when, state):
        if "disable_reminders" in state.get("overrides", []) or any(
            isinstance(o, dict) and o.get("kind") == "disable_reminders" for o in state.get("overrides", [])
        ): return []
        out = []; minute = when.hour * 60 + when.minute
        for b in self.schedule.routine:
            start, end = b.start_minutes, b.end_minutes
            if (b.reminder.get("enabled") or b.id in ("breakfast", "sleep")) and minute in ((start - 5) % 1440, start, (end - 5) % 1440):
                kind = "pre" if minute == (start - 5) % 1440 else ("start" if minute == start else "wrap")
                text = (f"{b.title} starts in five minutes ({b.subject or b.title.lower()})." if kind == "pre"
                        else f"{b.title} starts now." if kind == "start" else f"Five minutes left in {b.title}.")
                out.append(Reminder(f"{b.id}:{kind}", kind, text, b))
        for b in self.schedule.routine:
            if minute == (b.end_minutes - 1) % 1440 and b.category not in ("sleep",) and b.end_minutes != b.start_minutes:
                out.append(Reminder(f"{b.id}:end", "end", f"{b.title} is complete. {self.schedule.next_block_after(when).title} next.", b))
        if self.hydration_cfg.get("enabled") and minute % int(self.hydration_cfg.get("interval_minutes", 30)) == 0:
            b = self.schedule.block_at(when)
            if b.category not in ("sleep", "pooja", "meal") and not state.get("last_hydration"):
                out.append(Reminder(f"hydrate:{when:%H:%M}", "hydrate", "Time to drink some water."))
        if when.hour == 4 and when.minute == 45:
            out.append(Reminder("morning", "morning", "Good morning, sir."))
        return [r for r in out if r.key not in state.get("fired", [])]


class FocusManager:
    def __init__(self, schedule): self.schedule = schedule
    def focus_state(self, when):
        b = self.schedule.block_at(when); minute = when.hour * 60 + when.minute
        if minute == 10 * 60 + 15:
            return FocusState("BREAK_ACTIVE", block_id="break")
        if b.category == "sleep": return FocusState("SLEEP", block_id=b.id)
        if b.category == "study":
            remaining = ((b.end_minutes - minute) % 1440) * 60
            mode = "STUDY_ENDING" if remaining <= 5 * 60 else ("STUDY_STARTING" if minute - b.start_minutes < 5 else "STUDY_ACTIVE")
            return FocusState(mode, b.subject, remaining, b.id)
        if b.category == "break": return FocusState("BREAK_ACTIVE", block_id=b.id)
        return FocusState("STUDY_COMPLETE" if b.category == "meal" else "IDLE", block_id=b.id)


class DistractionResult:
    def __init__(self, kind, level=0, suggestion=""): self.kind, self.level, self.suggestion = kind, level, suggestion


class DistractionMonitor:
    def __init__(self, schedule, config=None): self.schedule, self.config = schedule, config or {}; self._seen = {}
    def evaluate(self, when, window):
        if when.hour == 10 and when.minute == 15:
            return DistractionResult("NOT_MONITORED")
        b = self.schedule.block_at(when)
        if not self.config.get("enabled", True) or not b.monitor_distractions: return DistractionResult("NOT_MONITORED")
        text = f"{window.app} {window.title} {window.url}".lower()
        educational = any(x in text for x in ("khan academy", "chemistry", "physics", "lecture", "tutorial"))
        if educational or any(x in text for x in ("calculator", "notepad", "notes")): return DistractionResult("SUPPORTED")
        if any(x in text for x in ("instagram", "twitter", "x.com", "funny", "cartoon", "entertainment", "youtube")):
            return DistractionResult("OUT_OF_SCHEDULE")
        return DistractionResult("UNKNOWN")
    def escalate(self, when, base, window):
        if base.kind != "OUT_OF_SCHEDULE": return base
        first = self._seen.setdefault(id(window), [when, 0])
        first[1] += 1
        elapsed = (when - first[0]).total_seconds()
        if first[1] == 1: return DistractionResult(base.kind, 1)
        if first[1] == 2:
            return DistractionResult(base.kind, 2, self.schedule.block_at(when).subject)
        if first[1] == 3 and not self.config.get("auto_return_enabled"): return DistractionResult(base.kind, 3, self.schedule.block_at(when).subject)
        if self.config.get("auto_return_enabled") and first[1] >= 4: return DistractionResult(base.kind, 4)
        return DistractionResult(base.kind, 3, self.schedule.block_at(when).subject)
