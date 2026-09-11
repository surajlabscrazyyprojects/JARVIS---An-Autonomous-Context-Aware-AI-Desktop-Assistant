from .model import FocusState, RoutineBlock, WindowObservation, block_covers
from .routine import (DailyStateManager, DistractionMonitor, FocusManager,
                      ReminderEngine, RoutineManager, ScheduleEngine)
from .profile import GoalManager, PersonalProfile, SpecialEventManager


class LifeAssistant:
    def __init__(self, directory, config=None):
        self.directory, self.config = directory, config or {}
        self.routines = RoutineManager(directory)
        self.schedule = ScheduleEngine(self.routines.routine)
        self.daily = DailyStateManager(directory)
        self.reminders = ReminderEngine(self.schedule, self.daily, self.config)
        self.focus = FocusManager(self.schedule)
        self.distraction = DistractionMonitor(self.schedule, self.config.get("distraction", {}))
        self.profile = PersonalProfile(directory)
        self.events = SpecialEventManager(self.profile)
        self.now_fn = __import__("datetime").datetime.now
        self._notifier = None
        self._exam = False

    def set_notifier(self, fn): self._notifier = fn
    def _day(self, when): return self.daily.day(when.date())
    def tick(self, when=None):
        when = when or self.now_fn(); state = self._day(when); out = []
        for r in self.reminders.due(when, state):
            state["fired"].append(r.key); out.append({"kind": "reminder", "reminder": {"text": r.text, "kind": r.kind}})
        b = self.schedule.block_at(when)
        for completed in self.routines.routine:
            if completed.category == "study" and when.hour * 60 + when.minute == completed.end_minutes:
                if completed.id not in state["completed"]: state["completed"].append(completed.id)
        for e in self.events.upcoming(0, when.date()):
            if e["date"] == str(when.date()): out.append({"kind": "reminder", "reminder": {"text": e["title"], "kind": "event"}})
        event = {"kind": "state", "state": self.state(when)}; out.append(event)
        self.daily._save()
        if self._notifier: self._notifier(out)
        return out

    def state(self, when=None):
        when = when or self.now_fn(); b = self.schedule.block_at(when); focus = self.focus.focus_state(when)
        overrides = []
        for value in self.daily.data.values():
            overrides.extend(value.get("overrides", []))
        return {"date": str(when.date()), "current": {"id": b.id, "title": b.title, "remaining_seconds": focus.remaining_seconds},
                "next": {"id": self.schedule.next_block_after(when).id}, "focus": vars(focus),
                "distraction": {}, "progress": {"total": len(self.routines.routine), "completed": len(self._day(when)["completed"])},
                "hydration": {"count": self._day(when)["hydration"]}, "last_reminder": None,
                "overrides": overrides, "mode": "EXAM" if self._exam else "NORMAL",
                "sleeping": focus.mode == "SLEEP", "exceptions_today": self._day(when)["exceptions"]}

    def handle_command(self, kind, text, params=None):
        text = text.lower(); params = params or {}; day = self._day(self.now_fn())
        if kind == "routine_override":
            if "skip" in text: day["overrides"].append("skip_block"); reply = "Understood, sir. That subject is skipped today."
            elif "ignore" in text: day["overrides"].append("disable_reminders"); reply = "Understood, sir. The routine is ignored today."
            elif "extra break" in text: day["overrides"].append("extra_break"); reply = "Extra break added, sir."
            elif "move" in text: day["overrides"].append("shift"); reply = "Chemistry moved, sir."
            elif "enable exam" in text: self._exam = True; reply = "EXAM MODE enabled, sir."
            elif "disable exam" in text: self._exam = False; reply = "Exam mode disabled, sir."
            else: reply = "Routine override noted, sir."
        elif kind == "hydration_ack":
            if "interval" in text and "interval" in params: self.config.setdefault("hydration", {})["interval_minutes"] = params["interval"]; reply = f"Water reminder interval set to {params['interval']} minutes."
            else: self.daily.record_hydration_ack(self.now_fn().date(), self.now_fn()); reply = "Water logged, sir."
        elif kind == "routine_status":
            b = self.schedule.block_at(self.now_fn()); reply = f"You are in {b.title}; {self.focus.focus_state(self.now_fn()).remaining_seconds} seconds remaining."
        elif kind == "show_routine":
            reply = "\n".join(f"{b.start} {b.title}" for b in self.routines.routine)
        else: reply = "Understood, sir."
        self.daily._save(); return reply, {}

    def acknowledge_distraction(self, text, now=None):
        self._day(now or self.now_fn())["exceptions"] += 1; self.daily._save()
        if "break" in text.lower(): return "Understood. Your next scheduled break is at 15:30."
        return "Understood, sir. I’ll allow this exception."

    def exam_mode(self): return self._exam
