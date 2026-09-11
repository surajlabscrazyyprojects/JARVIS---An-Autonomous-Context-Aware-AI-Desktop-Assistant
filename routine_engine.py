"""
J.A.R.V.I.S. Daily Routine + Reminder Engine
=============================================

Deterministic, backend-authoritative core for the Daily Routine and Reminder
system. It is intentionally free of any AI/LLM calls for scheduling logic
(timestamp math, state transitions, reminder firing are all deterministic).

Key design rules (per spec):
  * One authoritative system clock.
  * state = f(current_time), recomputed every tick; never "decrement a counter".
  * Every routine start / reminder trigger is deduplicated via
    event_id = routine_id|block_id + scheduled_timestamp (+ date).
  * Persists to JSON under ``memory/`` so it survives restart / refresh.
  * Separate BASE ROUTINE (fixed timetable) from TODAY'S INSTANCE (progress,
    overrides, completion) and HISTORY (past days).
  * A ``warp`` factor compresses time for accelerated testing.

The engine only *emits events* (as plain dicts). Audio playback, TTS voice,
character animation and UI live in the HUD; the backend never plays sound.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
MEMORY_DIR = ROOT / "memory"
INSTANCE_FILE = MEMORY_DIR / "routine_instance.json"
REMINDERS_FILE = MEMORY_DIR / "reminders.json"
HISTORY_FILE = MEMORY_DIR / "routine_history.json"
QUOTES_FILE = MEMORY_DIR / "routine_quotes.json"
SETTINGS_FILE = MEMORY_DIR / "reminder_settings.json"

# --------------------------------------------------------------------------
# Base timetable (the fixed daily schedule). Sleep wraps past midnight.
# --------------------------------------------------------------------------
BASE_ROUTINE: List[Dict[str, Any]] = [
    {"id": "wake",        "start": "04:45", "end": "05:00", "title": "Wake up",                 "subject": "Water / Washroom",        "type": "routine", "chime": True},
    {"id": "brush",       "start": "05:00", "end": "05:15", "title": "Brush",                  "subject": "Basic hygiene",          "type": "routine", "chime": True},
    {"id": "yoga",        "start": "05:15", "end": "05:30", "title": "Yoga",                   "subject": "Stretching",             "type": "routine", "chime": True},
    {"id": "pooja",       "start": "05:30", "end": "06:30", "title": "Pooja",                  "subject": "",                      "type": "routine", "chime": True},
    {"id": "bath",        "start": "06:30", "end": "06:50", "title": "Bath",                   "subject": "Skincare / self-care",  "type": "routine", "chime": True},
    {"id": "setup",       "start": "06:50", "end": "07:00", "title": "Light snack & setup",    "subject": "Nuts / study prep",      "type": "routine", "chime": True},
    {"id": "chemistry",   "start": "07:00", "end": "09:30", "title": "Chemistry Deep Study",   "subject": "Chemistry",              "type": "study",   "chime": True},
    {"id": "breakfast",   "start": "09:30", "end": "10:00", "title": "Breakfast",              "subject": "",                      "type": "meal",    "chime": True},
    {"id": "yt_break",    "start": "10:00", "end": "10:30", "title": "Entertainment Break",    "subject": "YouTube",               "type": "break",   "chime": True},
    {"id": "maths",       "start": "10:30", "end": "12:30", "title": "Mathematics Deep Study", "subject": "Mathematics",            "type": "study",   "chime": True},
    {"id": "lunch",       "start": "12:30", "end": "13:00", "title": "Lunch",                  "subject": "",                      "type": "meal",    "chime": True},
    {"id": "rest",        "start": "13:00", "end": "13:30", "title": "Rest",                  "subject": "Controlled entertainment","type": "break",  "chime": True},
    {"id": "physics",     "start": "13:30", "end": "15:30", "title": "Physics Deep Study",     "subject": "Physics",               "type": "study",   "chime": True},
    {"id": "meal_snack",  "start": "15:30", "end": "16:00", "title": "Meal / Snack",           "subject": "",                      "type": "meal",    "chime": True},
    {"id": "physics_rev", "start": "16:00", "end": "17:00", "title": "Physics Continuation",   "subject": "Revision / Questions",   "type": "study",   "chime": True},
    {"id": "teaching",    "start": "17:00", "end": "18:00", "title": "Teaching",               "subject": "",                      "type": "routine", "chime": True},
    {"id": "tea",         "start": "18:00", "end": "18:30", "title": "Break + Tea",            "subject": "Snack",                 "type": "break",   "chime": True},
    {"id": "physics_pyq", "start": "18:30", "end": "19:30", "title": "Physics PYQs",           "subject": "Practice / Revision",    "type": "study",   "chime": True},
    {"id": "chem_pyq",    "start": "19:30", "end": "20:30", "title": "Chemistry PYQs",         "subject": "Practice / Revision",    "type": "study",   "chime": True},
    {"id": "maths_pyq",   "start": "20:30", "end": "21:00", "title": "Maths PYQs",             "subject": "Practice / Revision",    "type": "study",   "chime": True},
    {"id": "dinner",      "start": "21:00", "end": "21:30", "title": "Dinner",                 "subject": "",                      "type": "meal",    "chime": True},
    {"id": "relax",       "start": "21:30", "end": "21:45", "title": "Relaxation",             "subject": "YouTube (limited)",      "type": "break",   "chime": True},
    {"id": "winddown",    "start": "21:45", "end": "22:00", "title": "Prepare Tomorrow",       "subject": "Hygiene / wind-down",    "type": "routine", "chime": True},
    {"id": "sleep",       "start": "22:00", "end": "04:45", "title": "Sleep",                  "subject": "Rest cycle",             "type": "sleep",   "chime": False},
]

# Statuses
PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
MISSED = "missed"
SKIPPED = "skipped"
PAUSED = "paused"

COMPLETION_MODES = ("auto_complete", "user_confirmation", "hybrid")
DEFAULT_COMPLETION_MODE = "hybrid"

QUOTES: List[str] = [
    "Discipline is the bridge between goals and accomplishment.",
    "Small daily improvements are the key to staggering long-term results.",
    "You do not rise to the level of your goals; you fall to the level of your systems.",
    "The secret of getting ahead is getting started.",
    "Focus is about saying no to a thousand good ideas to finish one.",
    "A little progress each day adds up to big results.",
    "Consistency beats intensity. Show up for the work, every single day.",
    "The expert in anything was once a beginner who refused to quit.",
    "Plan your work and work your plan; the day belongs to the prepared.",
    "Rest is part of the work. Recover so you can return sharper.",
    "Knowledge compounds. Every concept you master today pays dividends tomorrow.",
    "Do not count the hours; make the hours count.",
]


# --------------------------------------------------------------------------
# Data helpers
# --------------------------------------------------------------------------
def _hhmm_to_minutes(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _parse_time(s: str) -> Optional[str]:
    """Accept 'HH:MM', '7pm', '19:00', '7:30 am' -> normalized 'HH:MM' or None."""
    if s is None:
        return None
    s = s.strip().lower().replace(" ", "")
    m = re.match(r"^(\d{1,2}):?(\d{2})?(am|pm)?$", s)
    if not m:
        return None
    h = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mm > 59:
        return None
    return f"{h:02d}:{mm:02d}"


_TIME_DT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})$")


def _split_datetime_value(value) -> tuple:
    """Return (date_str|None, time_str|None) for a user-supplied datetime.

    Accepts datetime-local ('2026-09-02T18:00'), ISO ('2026-09-02 18:00'),
    or a bare time ('18:00', '6 pm'). Time-only inputs get date_str=None.
    """
    if isinstance(value, str):
        m = _TIME_DT_RE.match(value.strip())
        if m:
            y, mo, d, h, mi = m.groups()
            time_str = _parse_time(f"{int(h):02d}:{mi}")
            if time_str:
                return (f"{y}-{mo}-{d}", time_str)
    return (None, _parse_time(value))


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _now_local() -> datetime:
    return datetime.now()


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
class RoutineEngine:
    def __init__(self, memory_dir: Path = MEMORY_DIR):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.instance_file = self.memory_dir / "routine_instance.json"
        self.reminders_file = self.memory_dir / "reminders.json"
        self.history_file = self.memory_dir / "history.json"
        self.quotes_file = self.memory_dir / "quotes.json"

        self.lock = threading.RLock()

        self.warp = 1.0
        self._real_anchor: Optional[datetime] = None
        self._sim_anchor: Optional[datetime] = None

        self._last_state: Optional[Dict[str, Any]] = None
        self._last_greeting_sent = False

        # in-memory mirrors
        self.instance: Dict[str, Any] = self._load_instance()
        self.reminders: List[Dict[str, Any]] = self._load_reminders()
        self.history: Dict[str, Any] = self._load_history()
        self._quotes_state: Dict[str, Any] = self._load_quotes()
        self.settings: Dict[str, Any] = self._load_settings()

        # ensure today's instance exists
        self._ensure_instance_for_today(_now_local())

    # -- clock / warp ----------------------------------------------------
    def now(self) -> datetime:
        if self.warp == 1.0 or self._real_anchor is None:
            return _now_local()
        real_now = _now_local()
        elapsed = (real_now - self._real_anchor).total_seconds() * self.warp
        return self._sim_anchor + timedelta(seconds=elapsed)

    def set_warp(self, factor: float) -> None:
        """Compress time by `factor` (1 = real time). Used for accelerated tests."""
        with self.lock:
            if factor <= 0:
                factor = 1.0
            self._real_anchor = _now_local()
            self._sim_anchor = self.now()
            self.warp = float(factor)

    # -- persistence -----------------------------------------------------
    def _load_instance(self) -> Dict[str, Any]:
        try:
            if self.instance_file.exists():
                return json.loads(self.instance_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_instance(self) -> None:
        try:
            self.instance_file.write_text(json.dumps(self.instance, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_reminders(self) -> List[Dict[str, Any]]:
        try:
            if self.reminders_file.exists():
                data = json.loads(self.reminders_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _save_reminders(self) -> None:
        try:
            self.reminders_file.write_text(json.dumps(self.reminders, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_history(self) -> Dict[str, Any]:
        try:
            if self.history_file.exists():
                return json.loads(self.history_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_history(self) -> None:
        try:
            self.history_file.write_text(json.dumps(self.history, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_quotes(self) -> Dict[str, Any]:
        try:
            if self.quotes_file.exists():
                return json.loads(self.quotes_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"last_index": -1, "last_quote": ""}

    def _save_quotes(self) -> None:
        try:
            self.quotes_file.write_text(json.dumps(self._quotes_state, indent=2), encoding="utf-8")
        except Exception:
            pass

    # -- conversation-reminder settings -------------------------------
    def _load_settings(self) -> Dict[str, Any]:
        try:
            if SETTINGS_FILE.exists():
                d = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
        return {"conversation_reminders_enabled": "AUTO"}

    def _save_settings(self) -> None:
        try:
            SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_conversation_mode(self) -> str:
        m = self.settings.get("conversation_reminders_enabled", "AUTO")
        if m not in ("OFF", "CONFIRM", "AUTO"):
            m = "AUTO"
        return m

    def set_conversation_mode(self, mode: str) -> str:
        if mode not in ("OFF", "CONFIRM", "AUTO"):
            mode = "AUTO"
        self.settings["conversation_reminders_enabled"] = mode
        self._save_settings()
        return mode

    # -- daily instance --------------------------------------------------
    def _ensure_instance_for_today(self, now: datetime) -> None:
        today = _date_str(now)
        if self.instance.get("date") != today:
            self._archive_today()
            self.instance = {
                "date": today,
                "paused": False,
                "completion_mode": DEFAULT_COMPLETION_MODE,
                "overrides": {},
                "statuses": {},
                "muted_blocks": [],
                "reminders_ack": {},
                "last_greeting_date": "",
            }
            self._save_instance()

    def _archive_today(self) -> None:
        date = self.instance.get("date")
        if not date or date in self.history:
            return
        statuses = self.instance.get("statuses", {})
        completed, missed = [], []
        planned = 0
        done = 0
        for b in BASE_ROUTINE:
            if b["type"] == "sleep":
                continue
            planned += 1
            st = statuses.get(b["id"], COMPLETED)
            if st == COMPLETED:
                completed.append(b["id"])
                done += 1
            elif st in (MISSED, SKIPPED):
                missed.append(b["id"])
        self.history[date] = {
            "completed": completed,
            "missed": missed,
            "shifted": [],
            "planned_blocks": planned,
            "completed_blocks": done,
            "planned_minutes": sum(self._block_minutes(b) for b in BASE_ROUTINE if b["type"] != "sleep"),
            "completed_minutes": sum(self._block_minutes(b) for b in BASE_ROUTINE if b["type"] != "sleep" and b["id"] in completed),
        }
        self._save_history()

    @staticmethod
    def _block_minutes(b: Dict[str, Any]) -> int:
        return _hhmm_to_minutes(b["end"]) - _hhmm_to_minutes(b["start"])

    # -- block time helpers ---------------------------------------------
    def _block_interval(self, b: Dict[str, Any], now: datetime):
        """Return (start_dt, end_dt) for block on `now`'s date (handles sleep wrap)."""
        d = now.date()
        sh, sm = map(int, b["start"].split(":"))
        eh, em = map(int, b["end"].split(":"))
        start_dt = datetime(d.year, d.month, d.day, sh, sm)
        end_dt = datetime(d.year, d.month, d.day, eh, em)
        if end_dt <= start_dt:  # wraps midnight (sleep)
            end_dt += timedelta(days=1)
        return start_dt, end_dt

    # -- state computation ----------------------------------------------
    def compute_state(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        with self.lock:
            self._ensure_instance_for_today(now or self.now())
            now = now or self.now()
            date = _date_str(now)
            inst = self.instance
            paused = bool(inst.get("paused"))

            blocks = []
            current = None
            next_block = None
            completed_count = 0
            total_count = 0

            for b in BASE_ROUTINE:
                bid = b["id"]
                ostart = b["start"]
                oend = b["end"]
                override = inst.get("overrides", {}).get(bid, {})
                if override.get("start"):
                    ostart = override["start"]
                if override.get("end"):
                    oend = override["end"]

                d = now.date()
                sh, sm = map(int, ostart.split(":"))
                eh, em = map(int, oend.split(":"))
                start_dt = datetime(d.year, d.month, d.day, sh, sm)
                end_dt = datetime(d.year, d.month, d.day, eh, em)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                ts = int(start_dt.timestamp())
                te = int(end_dt.timestamp())
                now_ts = int(now.timestamp())

                forced = inst.get("statuses", {}).get(bid)
                if forced in (COMPLETED, MISSED, SKIPPED, PAUSED):
                    status = forced
                elif paused:
                    status = PAUSED if (start_dt <= now < end_dt) else (PENDING if now < start_dt else COMPLETED)
                else:
                    if now < start_dt:
                        status = PENDING
                    elif start_dt <= now < end_dt:
                        status = RUNNING
                    else:
                        status = COMPLETED

                entry = {
                    "id": bid,
                    "title": b["title"],
                    "subject": b.get("subject", ""),
                    "type": b.get("type", ""),
                    "start": ostart,
                    "end": oend,
                    "start_ts": ts,
                    "end_ts": te,
                    "status": status,
                    "chime": bool(b.get("chime", True)),
                }
                blocks.append(entry)

                if b["type"] != "sleep":
                    total_count += 1
                    if status == COMPLETED:
                        completed_count += 1

                if status == RUNNING and current is None:
                    current = entry
                elif status == PENDING and next_block is None:
                    next_block = entry

            if current is None and next_block is not None:
                current = next_block

            sleeping = bool(current and current["id"] == "sleep")
            remaining = 0
            if current:
                remaining = max(0, current["end_ts"] - int(now.timestamp()))

            return {
                "date": date,
                "mode": "normal",
                "sleeping": sleeping,
                "paused": paused,
                "completion_mode": inst.get("completion_mode", DEFAULT_COMPLETION_MODE),
                "blocks": blocks,
                "current": current or {},
                "next": next_block or {},
                "focus": {
                    "mode": "SLEEP" if sleeping else ("PAUSED" if paused else "FOCUS"),
                    "remaining_seconds": remaining,
                },
                "progress": {
                    "completed": completed_count,
                    "total": total_count,
                },
                "now_ts": now_ts,
            }

    # -- tick / transitions ---------------------------------------------
    def tick(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Advance the engine and return a list of events to emit."""
        with self.lock:
            now = now or self.now()
            self._ensure_instance_for_today(now)
            state = self.compute_state(now)
            events: List[Dict[str, Any]] = []

            # First tick after (re)start: establish baseline, do NOT replay history.
            if self._last_state is None:
                self._last_state = state
                g = self._greeting_if_due(now)
                if g:
                    events.append(g)
                return events

            prev_blocks = {b["id"]: b for b in self._last_state["blocks"]}
            cur_blocks = {b["id"]: b for b in state["blocks"]}

            for bid, b in cur_blocks.items():
                prev = prev_blocks.get(bid, {})
                if b["status"] == RUNNING and prev.get("status") != RUNNING:
                    if not self.instance.get("paused"):
                        events.append(self._routine_event("routine_started", b, now))
                elif prev.get("status") == RUNNING and b["status"] != RUNNING:
                    forced = self.instance.get("statuses", {}).get(bid)
                    if forced == MISSED:
                        events.append(self._routine_event("routine_missed", b, now))
                    else:
                        events.append(self._routine_event("routine_completed", b, now, outcome="completed"))
                        self._record_history_block(bid, COMPLETED)

            events.extend(self._check_reminders(now))

            g = self._greeting_if_due(now)
            if g:
                events.append(g)

            self._last_state = state
            return events

    def _routine_event(self, etype: str, block: Dict[str, Any], now: datetime,
                       outcome: str = "") -> Dict[str, Any]:
        event_id = f"{block['id']}:{block['start_ts']}:{etype}"
        return {
            "type": etype,
            "event_id": event_id,
            "block": {
                "id": block["id"], "title": block["title"], "subject": block.get("subject", ""),
                "start": block["start"], "end": block["end"],
                "start_ts": block["start_ts"], "end_ts": block["end_ts"],
                "chime": block.get("chime", True),
            },
            "outcome": outcome,
            "date": _date_str(now),
            "ts": int(now.timestamp()),
        }

    # -- reminders -------------------------------------------------------
    def get_reminders(self) -> List[Dict[str, Any]]:
        with self.lock:
            today = _date_str(self.now())
            out = []
            for r in sorted(self.reminders, key=lambda x: _hhmm_to_minutes(x["time"])):
                ack = self.instance.get("reminders_ack", {}).get(r["id"], {})
                if ack.get("date") == today and ack.get("status") in ("done", "dismissed"):
                    status = ack["status"]
                elif r.get("last_triggered_date") == today:
                    status = "triggered"
                else:
                    status = "scheduled"
                out.append({
                    "id": r["id"], "time": r["time"], "topic": r["topic"],
                    "enabled": r.get("enabled", True), "repeat": r.get("repeat", "none"),
                    "category": r.get("category", ""), "status": status,
                    "source": r.get("source", "MANUAL"),
                    "date": r.get("date"),
                    "last_triggered_date": r.get("last_triggered_date"),
                })
            return out

    def create_reminder(self, time: str, topic: str, repeat: str = "none",
                        category: str = "", source: str = "MANUAL",
                        date: Optional[str] = None) -> Dict[str, Any]:
        with self.lock:
            date_part, t = _split_datetime_value(time)
            if not t:
                raise ValueError("invalid time")
            topic = (topic or "").strip()
            if not topic:
                raise ValueError("empty topic")
            repeat = repeat if repeat in ("none", "daily", "weekly") else "none"
            if date_part and not date:
                date = date_part
            if date is None and repeat in ("daily", "weekly"):
                # Recurring reminders need a concrete next-occurrence target date
                # so they re-arm tomorrow / next week instead of firing daily.
                date = _date_str(self.now())
            r = {
                "id": uuid.uuid4().hex[:12],
                "time": t, "topic": topic, "enabled": True,
                "repeat": repeat,
                "category": category, "source": source, "date": date,
                "created_ts": int(self.now().timestamp()),
                "last_triggered_date": None,
            }
            self.reminders.append(r)
            self._save_reminders()
            return r

    def get_reminder(self, rid: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            for r in self.reminders:
                if r["id"] == rid:
                    return r
            return None

    def create_test_reminder(self, seconds: int = 10,
                             topic: str = "Dev Test Reminder") -> Dict[str, Any]:
        """Dev helper: create a reminder that fires ~`seconds` from now."""
        dt = self.now() + timedelta(seconds=seconds)
        return self.create_reminder(
            f"{dt.hour:02d}:{dt.minute:02d}", topic,
            source="SYSTEM", date=_date_str(dt),
        )

    def update_reminder(self, rid: str, **fields) -> Optional[Dict[str, Any]]:
        with self.lock:
            for r in self.reminders:
                if r["id"] == rid:
                    if "time" in fields and fields["time"] is not None:
                        date_part, t = _split_datetime_value(str(fields["time"]))
                        if not t:
                            raise ValueError("invalid time")
                        r["time"] = t
                        if date_part and "date" not in fields:
                            r["date"] = date_part
                    if "topic" in fields and fields["topic"] is not None:
                        r["topic"] = str(fields["topic"]).strip()
                    if "enabled" in fields:
                        r["enabled"] = bool(fields["enabled"])
                    if "repeat" in fields:
                        r["repeat"] = fields["repeat"] if fields["repeat"] in ("none", "daily", "weekly") else "none"
                    if "category" in fields:
                        r["category"] = str(fields["category"])
                    if "date" in fields:
                        r["date"] = fields["date"] or None
                    self._save_reminders()
                    return r
            return None

    def delete_reminder(self, rid: str) -> bool:
        with self.lock:
            before = len(self.reminders)
            self.reminders = [r for r in self.reminders if r["id"] != rid]
            if len(self.reminders) != before:
                self._save_reminders()
                return True
            return False

    def ack_reminder(self, rid: str, event_id: str, status: str) -> None:
        with self.lock:
            today = _date_str(self.now())
            self.instance.setdefault("reminders_ack", {})[rid] = {
                "event_id": event_id, "status": status, "date": today,
            }
            self._save_instance()

    def _check_reminders(self, now: datetime) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        today = _date_str(now)
        now_min = now.hour * 60 + now.minute
        for r in self.reminders:
            if not r.get("enabled", True):
                continue
            # Future-dated reminders are not yet due (fire only on their date).
            if r.get("date") and r["date"] != today:
                continue
            rh, rm = map(int, r["time"].split(":"))
            trig_min = rh * 60 + rm
            triggered_today = (r.get("last_triggered_date") == today)
            if now_min >= trig_min and not triggered_today:
                event_id = f"{r['id']}:{today}:{r['time']}"
                events.append({
                    "type": "reminder_triggered",
                    "event_id": event_id,
                    "reminder": {
                        "id": r["id"], "time": r["time"], "topic": r["topic"],
                        "repeat": r.get("repeat", "none"), "category": r.get("category", ""),
                        "source": r.get("source", "MANUAL"),
                    },
                    "date": today,
                    "ts": int(now.timestamp()),
                })
                r["last_triggered_date"] = today
                repeat = r.get("repeat", "none")
                if repeat == "none":
                    r["enabled"] = False
                else:
                    # One logical recurring reminder: advance the next-occurrence
                    # date instead of creating duplicates. DAILY -> tomorrow,
                    # WEEKLY -> exactly one week from today.
                    offset_days = 1 if repeat == "daily" else 7
                    next_dt = now + timedelta(days=offset_days)
                    r["date"] = _date_str(next_dt)
                self._save_reminders()
        return events

    # -- greeting --------------------------------------------------------
    def _greeting_if_due(self, now: datetime) -> Optional[Dict[str, Any]]:
        self._ensure_instance_for_today(now)
        today = _date_str(now)
        if self.instance.get("last_greeting_date") == today:
            return None
        self.instance["last_greeting_date"] = today
        self._save_instance()
        quote = self._next_quote()
        hour = now.hour
        if 4 <= hour < 12:
            greet = ("Good morning, sir. I hope today gives you another chance to learn "
                     "something new, grow more confident, and move one step closer to your goals.")
        elif 12 <= hour < 17:
            greet = "Good afternoon, sir. Steady progress beats frantic effort - let us keep the momentum."
        else:
            greet = "Good evening, sir. Another day of disciplined work is behind you. Let us finish strong."
        state = self.compute_state(now)
        cur = state.get("current") or {}
        nxt = state.get("next") or {}
        first = cur.get("title") or nxt.get("title") or "your first planned activity"
        intro = (f"Your first scheduled block is {first}. I'll keep you updated as each block begins, "
                 "and remind you of anything you've queued.")
        return {
            "type": "greeting",
            "event_id": f"greeting:{today}",
            "date": today,
            "greeting": greet,
            "quote": quote,
            "intro": intro,
            "ts": int(now.timestamp()),
        }

    def ack_greeting(self, date: str) -> None:
        with self.lock:
            self.instance["last_greeting_date"] = date
            self._save_instance()

    def _next_quote(self) -> str:
        idx = self._quotes_state.get("last_index", -1)
        nxt = (idx + 1) % len(QUOTES)
        if QUOTES[nxt] == self._quotes_state.get("last_quote") and len(QUOTES) > 1:
            nxt = (nxt + 1) % len(QUOTES)
        self._quotes_state["last_index"] = nxt
        self._quotes_state["last_quote"] = QUOTES[nxt]
        self._save_quotes()
        return QUOTES[nxt]

    def get_greeting_if_due(self, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self._greeting_if_due(now or self.now())

    # -- overrides -------------------------------------------------------
    def apply_override(self, block_id: str, action: str, **params) -> Dict[str, Any]:
        with self.lock:
            bid = block_id
            if not any(b["id"] == bid for b in BASE_ROUTINE):
                raise ValueError("unknown block")
            overrides = self.instance.setdefault("overrides", {})
            statuses = self.instance.setdefault("statuses", {})
            today = _date_str(self.now())

            if action == "skip":
                overrides[bid] = {"action": "skip", "status": SKIPPED, "date": today}
                statuses[bid] = SKIPPED
            elif action == "mark_complete":
                statuses[bid] = COMPLETED
                self._record_history_block(bid, COMPLETED)
            elif action == "mark_missed":
                statuses[bid] = MISSED
                self._record_history_block(bid, MISSED)
            elif action == "move":
                start = params.get("start")
                end = params.get("end")
                if start:
                    start = _parse_time(start)
                if end:
                    end = _parse_time(end)
                if not start or not end:
                    raise ValueError("move requires valid start and end")
                overrides[bid] = {"action": "move", "start": start, "end": end, "date": today}
            elif action == "extend":
                mins = int(params.get("minutes", 30))
                cur = overrides.get(bid, {})
                base_end = cur.get("end") or next(b["end"] for b in BASE_ROUTINE if b["id"] == bid)
                eh, em = map(int, base_end.split(":"))
                tot = eh * 60 + em + mins
                new_end = f"{(tot // 60) % 24:02d}:{tot % 60:02d}"
                overrides[bid] = {"action": "extend", "start": cur.get("start"), "end": new_end, "date": today}
            elif action == "mute":
                muted = self.instance.setdefault("muted_blocks", [])
                if bid not in muted:
                    muted.append(bid)
            elif action == "unmute":
                self.instance["muted_blocks"] = [x for x in self.instance.get("muted_blocks", []) if x != bid]
            elif action == "pause":
                self.instance["paused"] = True
            elif action == "resume":
                self.instance["paused"] = False
            else:
                raise ValueError("unknown action")
            self._save_instance()
            return self.compute_state()

    def set_completion_mode(self, mode: str) -> Dict[str, Any]:
        with self.lock:
            if mode not in COMPLETION_MODES:
                raise ValueError("invalid mode")
            self.instance["completion_mode"] = mode
            self._save_instance()
            return self.compute_state()

    def resume(self) -> Dict[str, Any]:
        with self.lock:
            self.instance["paused"] = False
            self._save_instance()
            return self.compute_state()

    def _record_history_block(self, bid: str, status: str) -> None:
        date = self.instance.get("date")
        rec = self.history.setdefault(date, {
            "completed": [], "missed": [], "shifted": [],
            "planned_blocks": 0, "completed_blocks": 0, "planned_minutes": 0, "completed_minutes": 0,
        })
        lst = rec["completed"] if status == COMPLETED else rec["missed"]
        if bid not in lst:
            lst.append(bid)
        self._save_history()

    def completion_response(self, block_id: str, outcome: str) -> Dict[str, Any]:
        """User answers 'how did it go?' -> update status accordingly."""
        with self.lock:
            statuses = self.instance.setdefault("statuses", {})
            if outcome in ("good", "done", "completed", "yes"):
                statuses[block_id] = COMPLETED
                self._record_history_block(block_id, COMPLETED)
            elif outcome in ("missed", "bad", "skip", "no"):
                statuses[block_id] = MISSED
                self._record_history_block(block_id, MISSED)
            self._save_instance()
            return self.compute_state()

    # -- natural-language intent (deterministic) -------------------------
    def handle_intent(self, text: str) -> Optional[str]:
        """Return a deterministic response string, or None to fall through to LLM."""
        t = (text or "").strip().lower()
        if not t:
            return None
        state = self.compute_state()
        cur = state.get("current") or {}
        nxt = state.get("next") or {}

        if re.search(r"what(?:'s| is|s)?\s+(?:my\s+)?routine\s+today", t) or "daily routine" in t:
            lines = [f"{b['start']}-{b['end']} {b['title']}" for b in state["blocks"] if b["type"] != "sleep"][:6]
            return "Today's plan, sir: " + "; ".join(lines) + ". I'll keep you posted as each block begins."

        if re.search(r"what(?:'s| is|s)?\s+(?:my\s+)?next", t) or "what comes next" in t:
            if nxt:
                return (f"Next up is {nxt['title']} from {nxt['start']} to {nxt['end']}, sir. "
                        f"Your current block is {cur.get('title', 'nothing')}.")
            return "You have no further scheduled blocks today, sir."

        if re.search(r"how\s+much\s+time|time\s+left|how\s+long", t):
            rem = state["focus"]["remaining_seconds"]
            if cur:
                return f"You have {rem // 3600}h {(rem % 3600)//60}m left in {cur['title']}, sir."
            return "There is no active block right now, sir."

        if re.search(r"what\s+am\s+i\s+(?:doing|supposed to be doing)|current routine|what now|doing now", t):
            if cur:
                return f"You should currently be on {cur['title']} ({cur['start']}-{cur['end']}), sir."
            return "No active routine right now, sir. Enjoy the gap."

        m = re.search(r"(?:mark|set)\s+(.+?)\s+(complete|done|finished)", t)
        if m:
            bid = self._find_block(m.group(1))
            if bid:
                self.apply_override(bid, "mark_complete")
                return f"Noted, sir. I've marked {bid.replace('_',' ')} as completed."

        if "skip" in t:
            m2 = re.search(r"skip\s+(.+)", t)
            target = (m2.group(1) if m2 else None) or cur.get("title")
            if target:
                bid = self._find_block(target) or (cur.get("id") if cur else None)
                if bid:
                    self.apply_override(bid, "skip")
                    return f"Understood, sir. I've skipped {bid.replace('_',' ')}."

        if "pause" in t and "routine" in t:
            self.instance["paused"] = True
            self._save_instance()
            return "Paused today's routine, sir. Say resume to continue."
        if "resume" in t and "routine" in t:
            self.resume()
            return "Resumed the routine, sir."

        m = re.search(r"remind me (?:at|on|by)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+to\s+(.+)", t)
        if m:
            time_str = _parse_time(m.group(1))
            topic = m.group(2).strip().rstrip('.')
            if time_str and topic:
                self.create_reminder(time_str, topic)
                return f"Your reminder is set for {time_str}: {topic}."
        m = re.search(r"remind me (?:to|that)\s+(.+?)\s+(?:at|by|on)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", t)
        if m:
            topic = m.group(1).strip().rstrip('.')
            time_str = _parse_time(m.group(2))
            if time_str and topic:
                self.create_reminder(time_str, topic)
                return f"Your reminder is set for {time_str}: {topic}."
        m = re.search(r"remind me (?:in|after)\s+(\d+)\s*(minute|min|hour|hr)", t)
        if m:
            n = int(m.group(1))
            unit = m.group(2)
            now = self.now()
            delta = timedelta(minutes=n) if unit.startswith("min") else timedelta(hours=n)
            tt = now + delta
            time_str = f"{tt.hour:02d}:{tt.minute:02d}"
            tm2 = re.search(r"remind me (?:in|after)\s+\d+\s*(?:minute|min|hour|hr)s?\s+to\s+(.+)", t)
            topic = tm2.group(1).strip().rstrip('.') if tm2 else "Reminder"
            self.create_reminder(time_str, topic)
            return f"Your reminder is set for {time_str}: {topic}."
        return None

    def _find_block(self, phrase: str) -> Optional[str]:
        phrase = phrase.lower()
        best = None
        for b in BASE_ROUTINE:
            title = b["title"].lower()
            if phrase in title or title in phrase:
                return b["id"]
            subj = (b.get("subject") or "").lower()
            if subj and (phrase in subj or subj in phrase):
                best = best or b["id"]
        return best

    # -- history ---------------------------------------------------------
    def get_history(self, days: int = 7) -> Dict[str, Any]:
        with self.lock:
            keys = sorted(self.history.keys(), reverse=True)[:days]
            return {k: self.history[k] for k in keys}


def make_engine(memory_dir: Optional[Path] = None) -> RoutineEngine:
    return RoutineEngine(memory_dir or MEMORY_DIR)


if __name__ == "__main__":
    eng = make_engine()
    st = eng.compute_state()
    print("date:", st["date"])
    print("current:", st["current"].get("title"))
    print("progress:", st["progress"])
    print("events on tick:", len(eng.tick()))
