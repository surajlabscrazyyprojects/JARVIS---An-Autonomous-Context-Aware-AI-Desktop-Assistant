"""Tests for context-aware conversational reminder intelligence.

Covers spec TEST 1-10 (auto-create, ask-time, no-reminder-might,
friend-event-skip, gym-high-conf, someday-skip, Hinglish, kal-test-ask,
update-existing, duplicate-once) plus confidence/dedupe/clarify/settings.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routine_engine import RoutineEngine  # noqa: E402
from reminder_intel import ReminderIntel  # noqa: E402

FIXED = datetime(2026, 8, 30, 12, 0, 0)  # Sunday


def _make():
    # Isolate each test from persisted memory (reminders/settings on disk).
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mem = os.path.join(root, "memory")
    for fn in ("reminders.json", "reminder_settings.json", "routine_instance.json"):
        p = os.path.join(mem, fn)
        if os.path.exists(p):
            os.remove(p)
    eng = RoutineEngine()
    eng.warp = 1.0
    eng.now = lambda: FIXED  # deterministic "now"
    eng.set_conversation_mode("AUTO")
    return eng, ReminderIntel(eng)


def _tomorrow():
    return (FIXED + timedelta(days=1)).strftime("%Y-%m-%d")


def test_auto_create_with_time_and_forget():
    eng, intel = _make()
    res = intel.process_message(
        "I need to submit my assignment tomorrow at 5pm, don't let me forget")
    assert res["action"] == "create", res
    assert len(res["created"]) == 1
    r = res["created"][0]
    assert r["time"] == "17:00", r
    assert r["date"] == _tomorrow(), r
    assert r["source"] == "CONVERSATION", r


def test_ask_time_when_missing():
    eng, intel = _make()
    res = intel.process_message("I have to call the bank tomorrow")
    assert res["action"] == "clarify", res
    assert res["clarify"]["topic"]
    assert res["clarify"]["date"] == _tomorrow()


def test_no_reminder_for_might():
    eng, intel = _make()
    res = intel.process_message("I might go to the gym someday")
    assert res["action"] == "none"
    assert res["note"] == "hypothetical"


def test_skip_other_person_event():
    eng, intel = _make()
    res = intel.process_message("My friend has a test on Monday")
    assert res["action"] == "none"
    assert res["note"] == "other_person"


def test_gym_high_confidence():
    eng, intel = _make()
    res = intel.process_message("I have to go to the gym at 7am tomorrow")
    assert res["action"] == "create"
    r = res["created"][0]
    assert r["time"] == "07:00", r


def test_someday_skipped():
    eng, intel = _make()
    res = intel.process_message("Someday I will learn to play the piano")
    assert res["action"] == "none"


def test_hinglish_create():
    eng, intel = _make()
    res = intel.process_message("Mujhe kal 9 baje gym jaana hai")
    assert res["action"] == "create", res
    r = res["created"][0]
    assert r["time"] == "09:00", r
    assert r["date"] == _tomorrow(), r


def test_hinglish_ask_time():
    eng, intel = _make()
    res = intel.process_message("Meri test hai kal")
    assert res["action"] == "clarify", res
    assert res["clarify"]["date"] == _tomorrow()


def test_update_existing():
    eng, intel = _make()
    eng.create_reminder("09:00", "gym", source="MANUAL", date=_tomorrow())
    res = intel.process_message("I have to go to the gym at 7am tomorrow")
    assert res["action"] == "update", res
    assert len(res["updated"]) == 1
    assert res["updated"][0]["time"] == "07:00"


def test_duplicate_once():
    eng, intel = _make()
    eng.create_reminder("17:00", "submit assignment", source="CONVERSATION",
                        date=_tomorrow())
    res = intel.process_message(
        "I need to submit my assignment tomorrow at 5pm, don't let me forget")
    assert res["action"] == "none"
    assert res["duplicate"] is True
    assert len(eng.get_reminders()) == 1


def test_mode_off_disables_creation():
    eng, intel = _make()
    eng.set_conversation_mode("OFF")
    res = intel.process_message(
        "I need to submit my assignment tomorrow at 5pm, don't let me forget")
    assert res["action"] == "none"
    assert len(eng.get_reminders()) == 0


def test_detect_mode_command():
    eng, intel = _make()
    assert intel.detect_mode_command("turn off conversation reminders") == "OFF"
    assert intel.detect_mode_command("set conversation reminders to confirm") == "CONFIRM"
    assert intel.detect_mode_command("turn on conversation reminders auto") == "AUTO"
    assert intel.detect_mode_command("what time is it") is None


def test_explicit_remind_deferred_to_engine():
    eng, intel = _make()
    res = intel.process_message("Remind me to call mom at 9pm")
    assert res["action"] == "none"
    assert res["note"] is None
