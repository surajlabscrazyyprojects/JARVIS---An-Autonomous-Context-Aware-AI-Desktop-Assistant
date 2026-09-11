"""Tests for the deterministic Daily Routine + Reminder engine.

These verify the core scheduler logic WITHOUT a browser or network:
state computation, transition events + dedupe, reminder firing once,
overrides, persistence, daily reset, warp (accelerated mode) and the
deterministic NL intent handler.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routine_engine import RoutineEngine, COMPLETED, MISSED, SKIPPED, RUNNING  # noqa: E402


def _eng(tmp_path):
    return RoutineEngine(memory_dir=tmp_path)


def _eng_at(tmp_path, dt):
    """Engine whose clock is pinned to `dt` (keeps tests deterministic)."""
    e = RoutineEngine(memory_dir=tmp_path)
    e.now = lambda: dt
    e._ensure_instance_for_today(dt)
    return e


def test_compute_state_known_time(tmp_path):
    eng = _eng(tmp_path)
    now = datetime(2026, 1, 1, 7, 10, 0)
    st = eng.compute_state(now)
    assert st["current"]["title"] == "Chemistry Deep Study"
    assert st["current"]["status"] == RUNNING
    assert st["next"]["title"] == "Breakfast"
    assert st["progress"]["completed"] == 6
    assert st["progress"]["total"] == 23
    assert st["current"]["start_ts"] < st["current"]["end_ts"]
    assert st["current"]["end_ts"] - st["current"]["start_ts"] == 2 * 3600 + 30 * 60


def test_no_duplicate_start_event(tmp_path):
    eng = _eng(tmp_path)
    eng._last_state = None
    eng.tick(datetime(2026, 1, 1, 6, 59, 0))
    evs = eng.tick(datetime(2026, 1, 1, 7, 0, 0))
    types = [e["type"] for e in evs]
    assert "routine_started" in types
    started = [e for e in evs if e["type"] == "routine_started"]
    assert started[0]["block"]["id"] == "chemistry"
    evs2 = eng.tick(datetime(2026, 1, 1, 7, 0, 5))
    assert all(e["type"] != "routine_started" for e in evs2)


def test_reminder_fires_once(tmp_path):
    eng = _eng(tmp_path)
    eng.create_reminder("07:05", "Go to gym")
    evs0 = eng.tick(datetime(2026, 1, 1, 7, 4, 0))
    assert not any(e["type"] == "reminder_triggered" for e in evs0)
    evs1 = eng.tick(datetime(2026, 1, 1, 7, 5, 0))
    trig = [e for e in evs1 if e["type"] == "reminder_triggered"]
    assert len(trig) == 1
    assert trig[0]["reminder"]["topic"] == "Go to gym"
    evs2 = eng.tick(datetime(2026, 1, 1, 7, 6, 0))
    assert not any(e["type"] == "reminder_triggered" for e in evs2)


def test_overrides(tmp_path):
    now = datetime(2026, 1, 1, 8, 0, 0)
    eng = _eng_at(tmp_path, now)
    eng.apply_override("chemistry", "mark_complete")
    st = eng.compute_state(now)
    chem = next(b for b in st["blocks"] if b["id"] == "chemistry")
    assert chem["status"] == COMPLETED

    eng.apply_override("maths", "skip")
    st = eng.compute_state(now)
    maths = next(b for b in st["blocks"] if b["id"] == "maths")
    assert maths["status"] == SKIPPED

    eng.apply_override("physics", "move", start="13:00", end="14:00")
    st = eng.compute_state(now)
    phys = next(b for b in st["blocks"] if b["id"] == "physics")
    assert phys["start"] == "13:00" and phys["end"] == "14:00"

    eng.instance["paused"] = True
    eng._save_instance()
    st = eng.compute_state(now)
    assert st["paused"] is True


def test_persistence(tmp_path):
    eng = RoutineEngine(memory_dir=tmp_path)  # same real day -> survives reload
    eng.apply_override("chemistry", "mark_complete")
    assert (tmp_path / "routine_instance.json").exists()
    eng2 = RoutineEngine(memory_dir=tmp_path)
    st = eng2.compute_state()
    chem = next(b for b in st["blocks"] if b["id"] == "chemistry")
    assert chem["status"] == COMPLETED
    eng2.create_reminder("20:00", "Call Mom")
    assert any(r["topic"] == "Call Mom" for r in eng2.get_reminders())


def test_daily_reset_and_history(tmp_path):
    eng = _eng(tmp_path)
    eng.instance["date"] = "2000-01-01"
    eng.instance["statuses"] = {"chemistry": COMPLETED, "maths": MISSED}
    eng._save_instance()
    eng.tick(datetime(2026, 6, 15, 9, 0, 0))
    assert eng.instance["date"] == "2026-06-15"
    assert "2000-01-01" in eng.history
    hist = eng.history["2000-01-01"]
    assert "chemistry" in hist["completed"]
    assert "maths" in hist["missed"]


def test_warp_compresses_time(tmp_path):
    eng = _eng(tmp_path)
    eng.set_warp(60)
    t0 = eng.now()
    time.sleep(0.2)
    t1 = eng.now()
    diff = (t1 - t0).total_seconds()
    assert diff >= 5
    eng.set_warp(1)


def test_nl_intent(tmp_path):
    now = datetime(2026, 1, 1, 8, 0, 0)
    eng = _eng_at(tmp_path, now)
    r = eng.handle_intent("what's next")
    assert r and "Next up" in r
    r = eng.handle_intent("how much time is left")
    assert r and "left" in r.lower()
    r = eng.handle_intent("remind me at 9pm to call mom")
    assert r and any(x["topic"] == "call mom" for x in eng.get_reminders())
    r = eng.handle_intent("mark chemistry complete")
    assert r and "completed" in r.lower()
    st = eng.compute_state(now)
    assert next(b for b in st["blocks"] if b["id"] == "chemistry")["status"] == COMPLETED


def test_greeting_once_per_day(tmp_path):
    eng = _eng(tmp_path)
    now = datetime(2026, 1, 1, 8, 0, 0)
    g1 = eng._greeting_if_due(now)
    assert g1 and g1["type"] == "greeting" and g1["quote"]
    g2 = eng._greeting_if_due(now)
    assert g2 is None
